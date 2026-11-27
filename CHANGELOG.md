# Changelog

## [1.6.0](https://github.com/ASM-joynnovate/buddybird-ai-api/compare/v1.5.0...v1.6.0) (2026-11-27)


### Features

* 판정 컨테이너를 Cloudflare로 이전 ([48e73ca](https://github.com/ASM-joynnovate/buddybird-ai-api/commit/48e73ca9827c4edd85b0c51475bcb6feacf7ad6d))
* 판정 컨테이너를 Cloudflare로 이전 ([49100ac](https://github.com/ASM-joynnovate/buddybird-ai-api/commit/49100ac0decda16c9953a01a91414c2921787b10))

## [1.5.0](https://github.com/ASM-joynnovate/buddybird-ai-api/compare/v1.4.1...v1.5.0) (2026-10-28)


### Features

* 판별과 판정 점수를 앱 표시용 점수로 변환 [BB-771] ([cc4f5c1](https://github.com/ASM-joynnovate/buddybird-ai-api/commit/cc4f5c1c49f8f7e085a5b76f8b442d3f274bde36))
* 판별과 판정 점수를 앱 표시용 점수로 변환 [BB-771] ([b5c4494](https://github.com/ASM-joynnovate/buddybird-ai-api/commit/b5c4494983db92cf4198778e70aa43daa6fe3e38))


### Documentation

* 모사 판정 제한 시간을 300초로 변경 ([2fba36f](https://github.com/ASM-joynnovate/buddybird-ai-api/commit/2fba36f1de4d34d8c4b7b4be83247a216cc6856a))
* 모사 판정 제한 시간을 300초로 변경 ([a16b9fc](https://github.com/ASM-joynnovate/buddybird-ai-api/commit/a16b9fc6d077608c3d9a8e0c513a4cda216ba3b6))

## [1.4.1](https://github.com/ASM-joynnovate/buddybird-ai-api/compare/v1.4.0...v1.4.1) (2026-10-18)


### Bug Fixes

* 모사 판정 모델 파일을 비 root 사용자가 읽을 수 있게 복사 ([fa44487](https://github.com/ASM-joynnovate/buddybird-ai-api/commit/fa444872c1f248d4b7bac7f6daf688a22eeb9fb2))
* 모사 판정 모델 파일을 비 root 사용자가 읽을 수 있게 복사 ([0ba95f1](https://github.com/ASM-joynnovate/buddybird-ai-api/commit/0ba95f1dbe00cb82a6c992a755517ba42c0f99a2))

## [1.4.0](https://github.com/ASM-joynnovate/buddybird-ai-api/compare/v1.3.0...v1.4.0) (2026-10-18)


### Features

* 앵무새 소리 판별 결과에 analyzer_version 대신 model_version 전달 ([353b901](https://github.com/ASM-joynnovate/buddybird-ai-api/commit/353b9011f95e9bf28f32b64440f407627419a55e))
* 앵무새 소리 판별과 모사 판정을 Lambda 함수와 이미지로 분리 ([70ee4f2](https://github.com/ASM-joynnovate/buddybird-ai-api/commit/70ee4f24d0022a03486025b82d0e6d9edd16e9f4))
* 앵무새 소리 판별과 모사 판정을 Lambda 함수와 이미지로 분리 ([dad4bf1](https://github.com/ASM-joynnovate/buddybird-ai-api/commit/dad4bf15c9681d48d924aa9fd5aac3d2d9fe5dbe))

## [1.3.0](https://github.com/ASM-joynnovate/buddybird-ai-api/compare/v1.2.0...v1.3.0) (2026-10-18)


### Features

* **mimic:** 단어 모사 판정 모델 v1.0.0 연동 ([c05f62f](https://github.com/ASM-joynnovate/buddybird-ai-api/commit/c05f62f73102e11921efef9ec93bc988ee82b8e4))
* **mimic:** 단어 모사 판정 모델 v1.0.0 연동 [BB-694] ([057ae1f](https://github.com/ASM-joynnovate/buddybird-ai-api/commit/057ae1f33b982dce8422661e3e1fdcbe735de7e5))


### Bug Fixes

* Slack 배포 알림 커밋 목록 길이 제한 [BB-651] ([#25](https://github.com/ASM-joynnovate/buddybird-ai-api/issues/25)) ([4998dff](https://github.com/ASM-joynnovate/buddybird-ai-api/commit/4998dff9184f9e56b0417d2781d618022582453d))

## [1.2.0](https://github.com/ASM-joynnovate/buddybird-ai-api/compare/v1.1.0...v1.2.0) (2026-10-09)


### Features

* count calls split by breath gaps separately [BB-638] ([#23](https://github.com/ASM-joynnovate/buddybird-ai-api/issues/23)) ([38ca810](https://github.com/ASM-joynnovate/buddybird-ai-api/commit/38ca8103904e73d4b4f935f899853c2012a21f0d))

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
