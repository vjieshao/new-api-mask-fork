# New API Mask Proxy

Lightweight local reverse proxy for New API. It keeps real user groups and billing behavior unchanged, while masking group/rate displays in the user-facing console.

## Behavior

- `/api/user/self`: non-admin users see `group=default`.
- `/api/user/self/groups`: users only see the `default` group option.
- `/api/user/models`: rate/ratio fields are removed from user-facing model responses.
- `/api/log/self*`: log list shows `default` without `· 1x`; billing detail keeps `group_ratio=1` so it can display `分组倍率 1.0000x`.
- HTML pages get a small text cleaner that changes `专属倍率` to `分组倍率` and removes `· 1x` suffixes.

## Install

```bash
cp newapi-mask-proxy.py /root/newapi-mask-proxy.py
cp newapi-mask-proxy.service /etc/systemd/system/newapi-mask-proxy.service
systemctl daemon-reload
systemctl enable --now newapi-mask-proxy.service
```

Point Nginx for New API to the proxy:

```nginx
proxy_pass http://127.0.0.1:3002;
```

The upstream New API service remains on `127.0.0.1:3001`.
