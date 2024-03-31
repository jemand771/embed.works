# embed.works

## contributing

run backend services locally (redis as embed.works cache, minio for ufys):

```
docker run --rm -it -p 6379:6379 redis
docker run --rm -it -p 9080:9000 -e MINIO_ROOT_USER=minioadmin -e MINIO_ROOT_PASSWORD=minioadmin -e MINIO_DEFAULT_BUCKETS=test bitnami/minio
```