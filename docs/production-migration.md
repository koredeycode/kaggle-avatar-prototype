# Production migration

The notebook prototype deliberately omits durable auth, database storage, WebRTC/TURN, durable jobs, multi-session isolation, and managed observability. After the local loop is measured, move the provider contracts to a normal Python service, add PostgreSQL/Redis or equivalents, use authenticated WebRTC media, add model workers, and run load/security/chaos tests. Do not copy the Quick Tunnel security model into production.
