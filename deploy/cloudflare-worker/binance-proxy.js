const AUTH_HEADER = "X-Trading-Proxy-Key";

const ROUTES = [
  { prefix: "/fapi", upstream: "https://fapi.binance.com" },
  { prefix: "/dapi", upstream: "https://dapi.binance.com" },
  { prefix: "/demo-fapi", upstream: "https://demo-fapi.binance.com" },
  { prefix: "/testnet-future", upstream: "https://testnet.binancefuture.com" },
];

function notFound() {
  return new Response(null, {
    status: 404,
    headers: {
      "Cache-Control": "no-store",
    },
  });
}

function constantTimeEqual(left, right) {
  if (typeof left !== "string" || typeof right !== "string") {
    return false;
  }

  const maxLength = Math.max(left.length, right.length);
  let diff = left.length ^ right.length;
  for (let index = 0; index < maxLength; index += 1) {
    diff |= (left.charCodeAt(index) || 0) ^ (right.charCodeAt(index) || 0);
  }
  return diff === 0;
}

function matchRoute(pathname) {
  return ROUTES.find((route) => pathname === route.prefix || pathname.startsWith(`${route.prefix}/`));
}

function buildUpstreamUrl(sourceUrl, route) {
  const upstreamUrl = new URL(route.upstream);
  const strippedPath = sourceUrl.pathname.slice(route.prefix.length) || "/";
  upstreamUrl.pathname = strippedPath;
  upstreamUrl.search = sourceUrl.search;
  return upstreamUrl;
}

async function proxyRequest(request, env) {
  const expectedKey = env.TRADING_PROXY_KEY;
  const suppliedKey = request.headers.get(AUTH_HEADER);
  if (!constantTimeEqual(suppliedKey, expectedKey)) {
    return notFound();
  }

  const sourceUrl = new URL(request.url);
  const route = matchRoute(sourceUrl.pathname);
  if (!route) {
    return notFound();
  }

  const upstreamUrl = buildUpstreamUrl(sourceUrl, route);
  const headers = new Headers(request.headers);
  headers.delete(AUTH_HEADER);
  headers.delete("Host");
  headers.delete("CF-Connecting-IP");
  headers.delete("CF-IPCountry");
  headers.delete("CF-Ray");
  headers.delete("X-Forwarded-For");
  headers.delete("X-Real-IP");
  headers.set("Cache-Control", "no-store");
  headers.set("Pragma", "no-cache");

  const init = {
    method: request.method,
    headers,
    redirect: "manual",
    cf: {
      cacheTtl: 0,
      cacheEverything: false,
    },
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = request.body;
  }

  const upstreamResponse = await fetch(new Request(upstreamUrl.toString(), init));
  const responseHeaders = new Headers(upstreamResponse.headers);
  responseHeaders.set("Cache-Control", "no-store");
  responseHeaders.set("Pragma", "no-cache");

  return new Response(upstreamResponse.body, {
    status: upstreamResponse.status,
    statusText: upstreamResponse.statusText,
    headers: responseHeaders,
  });
}

export default {
  async fetch(request, env) {
    return proxyRequest(request, env);
  },
};
