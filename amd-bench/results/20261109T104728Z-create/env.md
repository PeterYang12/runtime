# Test environment

Recorded: 2026-11-09T10:47:28+00:00

## Host
- OS: Ubuntu 24.04.5 LTS
- Kernel: 6.8.0-142-generic
- Virtualization: kvm guest (DigitalOcean droplet); sandboxes run nested
- CPU: AMD EPYC 9555P 64-Core Processor, 64 vCPUs, 1 thread(s)/core
- Memory: 503 GiB total; hugepages 204800 x 2 MiB
- Storage: templates/snapshots on /dev/sda[/e2b] (4.9T, DigitalOcean block volume); root 80G
- Nodes: 1 (E2B Embed, docker compose)

## E2B stack
```
E2B_API_IMAGE=us-docker.pkg.dev/e2b-artifacts/api/api:v0.14.202610271447-39ad7ab6a67
E2B_ORCHESTRATOR_VERSION=v0.16.202610201713-75c97c0d1da
E2B_ENVD_VERSION=v0.9.202609130627-59497eb9134
E2B_KERNEL_VERSION=vmlinux-6.1.177_5008931
E2B_FIRECRACKER_VERSION=v1.14-0.2.0
HUGEPAGES=204800
NBDS_MAX=256
```
- Python SDK: e2b 2.46.0
- Client: same host, direct to api :3000 / client-proxy :3002 (no nginx, no WAN)
