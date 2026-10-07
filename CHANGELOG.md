# Changelog

## [1.1.0](https://github.com/ASM-joynnovate/buddybird-ai-api/compare/v1.0.0...v1.1.0) (2026-10-07)


### Features

* add Sentry tracing and judgment logs ([f5dd7e7](https://github.com/ASM-joynnovate/buddybird-ai-api/commit/f5dd7e7b9591b306ff7427a06074ee61afd042b5))
* add Sentry tracing and judgment logs [BB-618] ([b89af7f](https://github.com/ASM-joynnovate/buddybird-ai-api/commit/b89af7f203530e71108ad8f2f84694e4078e0015))

## 1.0.0 (2026-10-07)


### Features

* add docker image, arm64 ecr deploy workflow, and timezone batch [BB-498] ([#2](https://github.com/ASM-joynnovate/buddybird-ai-api/issues/2)) ([a2a0f89](https://github.com/ASM-joynnovate/buddybird-ai-api/commit/a2a0f89604bac9dcb6127065fd44ed67e7ea5e50))
* add fastapi foundation with health api [BB-493] ([#1](https://github.com/ASM-joynnovate/buddybird-ai-api/issues/1)) ([8580be4](https://github.com/ASM-joynnovate/buddybird-ai-api/commit/8580be4758428f6f621554bdf5c8302d2b66cbbf))
* add onset repeat-interval emergency candidate analysis [BB-495] ([#4](https://github.com/ASM-joynnovate/buddybird-ai-api/issues/4)) ([85f0e37](https://github.com/ASM-joynnovate/buddybird-ai-api/commit/85f0e37fc99118d40abcc233d4138c900490b162))
* integrate parrot-sound-gate and register OnsetService gRPC [BB-538] ([#7](https://github.com/ASM-joynnovate/buddybird-ai-api/issues/7)) ([7c81f40](https://github.com/ASM-joynnovate/buddybird-ai-api/commit/7c81f402061aee7cc1689f0ce8df1bc2492e8920))
* **onset:** add sqs cycle analysis worker [BB-544] ([#8](https://github.com/ASM-joynnovate/buddybird-ai-api/issues/8)) ([e66f1f9](https://github.com/ASM-joynnovate/buddybird-ai-api/commit/e66f1f920ac3aa8d652911f9cfb7d97059623bed))
* **onset:** add step1 loudness gate before parrot-sound-gate [BB-509] ([#11](https://github.com/ASM-joynnovate/buddybird-ai-api/issues/11)) ([288d702](https://github.com/ASM-joynnovate/buddybird-ai-api/commit/288d702e58b6d4ae18ad7461fb3fd4cdeef3f77c))
* **onset:** remove gRPC, add call_count, worker health check and direct DLQ [BB-552] ([#13](https://github.com/ASM-joynnovate/buddybird-ai-api/issues/13)) ([a99ffd4](https://github.com/ASM-joynnovate/buddybird-ai-api/commit/a99ffd458ed0ce1dfb0ebebbdf302887bebb9ca1))
* replace fastapi with grpc server and add onset proto [BB-458] ([#5](https://github.com/ASM-joynnovate/buddybird-ai-api/issues/5)) ([6e43ef2](https://github.com/ASM-joynnovate/buddybird-ai-api/commit/6e43ef2d6a361002a7c1da2dd364138decdbeff4))
* run sound analysis as a Lambda function for buddybird-api ([777a842](https://github.com/ASM-joynnovate/buddybird-ai-api/commit/777a84200a9246ca3b9cc2de1a5eaf923eb5b357))
* run sound analysis as a Lambda function for buddybird-api [BB-618] ([70a2cf1](https://github.com/ASM-joynnovate/buddybird-ai-api/commit/70a2cf1ca6d178aeb2388816abb21c77b46e9684))


### Miscellaneous Chores

* release 1.0.0 ([5b535f5](https://github.com/ASM-joynnovate/buddybird-ai-api/commit/5b535f535a0e9ad9ee3154a796ac32e3ec0b454a))
