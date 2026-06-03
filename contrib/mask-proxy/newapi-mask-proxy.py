#!/usr/bin/env python3
import http.client
import gzip
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


UPSTREAM_HOST = "127.0.0.1"
UPSTREAM_PORT = 3001
LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 3002


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self._proxy()

    def do_POST(self):
        self._proxy()

    def do_PUT(self):
        self._proxy()

    def do_PATCH(self):
        self._proxy()

    def do_DELETE(self):
        self._proxy()

    def do_OPTIONS(self):
        self._proxy()

    def do_HEAD(self):
        self._proxy()

    def log_message(self, fmt, *args):
        return

    def _proxy(self):
        body_len = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(body_len) if body_len else None

        headers = {k: v for k, v in self.headers.items()}
        headers.pop("Accept-Encoding", None)
        headers["Host"] = self.headers.get("Host", "newapi.ccicu.com")

        conn = http.client.HTTPConnection(UPSTREAM_HOST, UPSTREAM_PORT, timeout=120)
        try:
            conn.request(self.command, self.path, body=body, headers=headers)
            resp = conn.getresponse()
            resp_body = resp.read()
            resp_headers = resp.getheaders()
            out_body, modified = self._transform_response(resp_body, resp_headers)

            self.send_response(resp.status, resp.reason)
            for key, value in resp_headers:
                lk = key.lower()
                if lk in {"content-length", "transfer-encoding", "connection"}:
                    continue
                if modified and lk == "content-encoding":
                    continue
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(out_body)))
            self.send_header("Connection", "close")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(out_body)
        finally:
            conn.close()

    def _transform_response(self, resp_body, resp_headers):
        masked_body, masked = self._mask_user_response(resp_body, resp_headers)
        if masked:
            return masked_body, True
        return self._inject_cleaner(resp_body, resp_headers)

    def _inject_cleaner(self, resp_body, resp_headers):
        header_map = dict((k.lower(), v) for k, v in resp_headers)
        if "text/html" not in header_map.get("content-type", ""):
            return resp_body, False
        try:
            encoded = header_map.get("content-encoding", "")
            raw_body = gzip.decompress(resp_body) if encoded.lower() == "gzip" else resp_body
            html = raw_body.decode("utf-8")
            if "newapiMaskCleanRateSuffix" in html:
                return resp_body, False
            script = r'''<script id="newapiMaskCleanRateSuffix">
(function(){
  function cleanText(s){return s.replace(/专属倍率/g,'分组倍率').replace(/\s*·\s*1(?:\.0+)?x\b/gi,'');}
  function walk(n){
    if(n.nodeType===3){var v=cleanText(n.nodeValue); if(v!==n.nodeValue)n.nodeValue=v; return;}
    if(!n.childNodes || ['SCRIPT','STYLE','TEXTAREA','INPUT'].includes(n.nodeName))return;
    for(var i=0;i<n.childNodes.length;i++)walk(n.childNodes[i]);
  }
  function clean(){walk(document.body||document.documentElement);}
  new MutationObserver(clean).observe(document.documentElement,{childList:true,subtree:true,characterData:true});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',clean);else clean();
})();
</script>'''
            marker = "</body>"
            if marker in html:
                html = html.replace(marker, script + marker, 1)
            else:
                html += script
            return html.encode("utf-8"), True
        except Exception:
            return resp_body, False

    def _mask_user_response(self, resp_body, resp_headers):
        path = self.path.split("?", 1)[0]
        is_log_path = path.startswith("/api/log/self")
        if path not in {"/api/user/self", "/api/user/self/groups", "/api/user/models"} and not is_log_path:
            return resp_body, False
        try:
            encoded = dict((k.lower(), v) for k, v in resp_headers).get("content-encoding", "")
            raw_body = gzip.decompress(resp_body) if encoded.lower() == "gzip" else resp_body
            payload = json.loads(raw_body.decode("utf-8"))

            if path == "/api/user/self/groups":
                payload["data"] = {"default": "默认分组"}
                return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), True

            if is_log_path:
                if self._strip_rate_fields(payload, keep_group=True, force_rate_one=False):
                    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), True
                return resp_body, False

            if path == "/api/user/models":
                if self._strip_rate_fields(payload):
                    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), True
                return resp_body, False

            data = payload.get("data")
            if isinstance(data, dict) and int(data.get("role", 0) or 0) < 100:
                data["group"] = "default"
                return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), True
            return resp_body, False
        except Exception:
            return resp_body, False

    def _strip_rate_fields(self, value, keep_group=False, force_rate_one=False):
        changed = False
        if isinstance(value, dict):
            for key in list(value.keys()):
                lk = key.lower()
                if keep_group and lk in {"group", "using_group"}:
                    value[key] = "default"
                    changed = True
                elif lk in {"rate", "ratio", "model_ratio", "completion_ratio", "group_ratio", "using_group", "multiplier"} or "ratio" in lk or "rate" in lk or "multiplier" in lk:
                    if force_rate_one:
                        value[key] = 1
                    else:
                        value.pop(key, None)
                    changed = True
                else:
                    if keep_group and isinstance(value[key], str):
                        cleaned = self._clean_json_text(
                            value[key],
                            keep_group=keep_group,
                            force_rate_one=force_rate_one or key.lower() == "other",
                        )
                        cleaned = self._clean_rate_text(cleaned, force_rate_one=force_rate_one, remove_rate=True)
                        if cleaned != value[key]:
                            value[key] = cleaned
                            changed = True
                    changed = self._strip_rate_fields(value[key], keep_group=keep_group, force_rate_one=force_rate_one) or changed
        elif isinstance(value, list):
            for idx, item in enumerate(value):
                if keep_group and isinstance(item, str):
                    cleaned = self._clean_json_text(item, keep_group=keep_group, force_rate_one=force_rate_one)
                    cleaned = self._clean_rate_text(cleaned, force_rate_one=force_rate_one, remove_rate=True)
                    if cleaned != item:
                        value[idx] = cleaned
                        changed = True
                changed = self._strip_rate_fields(value[idx], keep_group=keep_group, force_rate_one=force_rate_one) or changed
        return changed

    def _clean_rate_text(self, value, force_rate_one=False, remove_rate=False):
        value = value.replace("专属倍率", "分组倍率")
        if remove_rate:
            if "分组倍率" in value:
                value = re.sub(r"分组倍率(?:\s*\d+(?:\.\d+)?x)?", "分组倍率 1.0000x", value, flags=re.IGNORECASE)
                value = re.sub(r"(分组倍率 1\.0000x)(?:\s*\d+(?:\.\d+)?x)+", r"\1", value, flags=re.IGNORECASE)
                return value
            value = re.sub(r"\s*[·|/,-]\s*\d+(?:\.\d+)?x\b", "", value, flags=re.IGNORECASE)
            value = re.sub(r"(?<=分组倍率)\s*\d+(?:\.\d+)?x\b", "", value, flags=re.IGNORECASE)
            return value
        if force_rate_one:
            value = re.sub(r"\s*[·|/,-]\s*\d+(?:\.\d+)?x\b", "", value, flags=re.IGNORECASE)
            value = re.sub(r"(?<=分组倍率)\s*\d+(?:\.\d+)?x\b", "", value, flags=re.IGNORECASE)
            return value
        return re.sub(r"\s*[·|/,-]\s*\d+(?:\.\d+)?x\b", "", value, flags=re.IGNORECASE)

    def _clean_json_text(self, value, keep_group=False, force_rate_one=False):
        text = value.strip()
        if not text or text[0] not in "[{":
            return value
        try:
            parsed = json.loads(value)
        except Exception:
            return value
        if self._strip_rate_fields(parsed, keep_group=keep_group, force_rate_one=force_rate_one):
            return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
        return value


if __name__ == "__main__":
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), ProxyHandler)
    server.serve_forever()
