import { DurableObject } from "cloudflare:workers";

interface Env {
	PARROT_DETECTION: DurableObjectNamespace<ParrotDetection>;
	MIMIC_JUDGMENT: DurableObjectNamespace<MimicJudgment>;
	JUDGMENT_RESULT: Queue;
}

const PORT = 8080;
const INACTIVITY_TIMEOUT_MS = 2 * 60 * 1000;
const READY_ATTEMPTS = 240;
const READY_INTERVAL_MS = 500;
const BUSY_RETRY_DELAY_SECONDS = 30;
const MIMIC_JUDGMENT_INSTANCES = 10;
const BUSY = 429;

abstract class Judge extends DurableObject<Env> {
	protected abstract readonly image: string;
	protected abstract readonly instance: { vcpu: number; memoryMib: number; diskMb: number };
	protected abstract readonly timeoutMs: number;

	private busy = false;
	private ready = false;

	async fetch(request: Request): Promise<Response> {
		if (this.busy) {
			return new Response(null, { status: BUSY });
		}
		this.busy = true;
		const judgment = this.judge(request).finally(() => {
			this.busy = false;
		});
		this.ctx.waitUntil(judgment);
		return judgment;
	}

	private async judge(request: Request): Promise<Response> {
		const container = this.ctx.container!;
		const message = await request.text();
		try {
			await this.ensureReady();
		} catch (error) {
			console.error(`${this.image} container is not ready`, error);
			return new Response(null, { status: 503 });
		}
		const signal = AbortSignal.timeout(this.timeoutMs);
		for (let attempt = 0; ; attempt++) {
			try {
				return await container.getTcpPort(PORT).fetch("http://container/", {
					method: "POST",
					headers: request.headers,
					body: message,
					signal,
				});
			} catch (error) {
				console.error(`${this.image} request failed`, error);
				if (attempt > 0 || signal.aborted) {
					await container.destroy();
					return new Response(null, { status: 502 });
				}
			}
		}
	}

	private async ensureReady(): Promise<void> {
		if (this.ready && this.ctx.container!.running) {
			await this.ctx.container!.setInactivityTimeout(INACTIVITY_TIMEOUT_MS);
			return;
		}
		this.ready = false;
		await this.start();
		this.ready = true;
	}

	private async start(): Promise<void> {
		const container = this.ctx.container!;
		if (!container.running) {
			container.start({
				image: container.images[this.image],
				instance: this.instance,
				enableInternet: true,
				env: Object.fromEntries(Object.entries(this.env).filter(([, value]) => typeof value === "string")),
			});
		}
		await container.setInactivityTimeout(INACTIVITY_TIMEOUT_MS);

		const port = container.getTcpPort(PORT);
		let lastError: unknown;
		for (let attempt = 0; attempt < READY_ATTEMPTS && container.running; attempt++) {
			try {
				const response = await port.fetch("http://container/healthz", { signal: AbortSignal.timeout(1000) });
				await response.body?.cancel();
				if (response.ok) {
					return;
				}
				lastError = new Error(`healthz returned ${response.status}`);
			} catch (error) {
				lastError = error;
			}
			await scheduler.wait(READY_INTERVAL_MS);
		}
		throw new Error("container did not become ready", { cause: lastError });
	}
}

export class ParrotDetection extends Judge {
	protected readonly image = "parrot-detection";
	protected readonly instance = { vcpu: 0.5, memoryMib: 2048, diskMb: 4000 };
	protected readonly timeoutMs = 60 * 1000;
}

export class MimicJudgment extends Judge {
	protected readonly image = "mimic-judgment";
	protected readonly instance = { vcpu: 2, memoryMib: 6144, diskMb: 8000 };
	protected readonly timeoutMs = 300 * 1000;
}

async function dispatch(judges: DurableObjectNamespace<Judge>, instances: number, message: Message): Promise<Response> {
	for (let index = 0; index < instances; index++) {
		const response = await judges.getByName(`instance-${index}`).fetch("http://judge/", {
			method: "POST",
			headers: { "X-Queue-Message-Id": message.id },
			body: JSON.stringify(message.body),
		});
		if (response.status !== BUSY) {
			return response;
		}
		await response.body?.cancel();
	}
	return new Response(null, { status: BUSY });
}

export default {
	async queue(batch, env): Promise<void> {
		const mimicry = batch.queue.endsWith("-mimicry-judgment");
		const judges: DurableObjectNamespace<Judge> = mimicry ? env.MIMIC_JUDGMENT : env.PARROT_DETECTION;
		const instances = mimicry ? MIMIC_JUDGMENT_INSTANCES : 1;
		for (const message of batch.messages) {
			try {
				const response = await dispatch(judges, instances, message);
				if (response.ok) {
					await env.JUDGMENT_RESULT.send(await response.json());
					message.ack();
					continue;
				}
				await response.body?.cancel();
				console.error("judgment failed", batch.queue, message.id, response.status);
				message.retry(response.status === BUSY ? { delaySeconds: BUSY_RETRY_DELAY_SECONDS } : undefined);
			} catch (error) {
				console.error("judgment failed", batch.queue, message.id, error);
				message.retry();
			}
		}
	},
} satisfies ExportedHandler<Env>;
