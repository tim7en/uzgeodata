export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname.startsWith("/data/")) {
      if (request.method !== "GET" && request.method !== "HEAD") {
        return new Response("Method not allowed", {
          status: 405,
          headers: { Allow: "GET, HEAD" }
        });
      }

      const key = decodeURIComponent(
        url.pathname.slice("/data/".length)
      );

      if (!key) {
        return new Response("Not found", { status: 404 });
      }

      const object = await env.DATA.get(key);

      if (!object) {
        return new Response("Not found", { status: 404 });
      }

      const headers = new Headers();
      object.writeHttpMetadata(headers);

      headers.set("etag", object.httpEtag);
      headers.set("cache-control", "public, max-age=3600");

      return new Response(
        request.method === "HEAD" ? null : object.body,
        { headers }
      );
    }

    return env.ASSETS.fetch(request);
  }
};