import { API_BASE_URL } from "@/lib/api";

const RESPONSE_HEADER_ALLOWLIST = ["content-type", "cache-control", "etag", "last-modified"];

type Params = {
  path: string[];
};

export async function GET(
  request: Request,
  { params }: { params: Promise<Params> },
): Promise<Response> {
  const { path } = await params;
  const upstreamPath = path.join("/");
  const upstreamUrl = new URL(`${API_BASE_URL}/${upstreamPath}`);
  const searchParams = new URL(request.url).searchParams;
  upstreamUrl.search = searchParams.toString();

  let upstreamResponse: Response;
  try {
    upstreamResponse = await fetch(upstreamUrl.toString(), {
      method: "GET",
      headers: {
        Accept: request.headers.get("accept") ?? "application/json",
      },
      cache: "no-store",
    });
  } catch {
    return Response.json(
      { error: "Failed to reach upstream API." },
      { status: 502 },
    );
  }

  const headers = new Headers();
  for (const name of RESPONSE_HEADER_ALLOWLIST) {
    const value = upstreamResponse.headers.get(name);
    if (value) headers.set(name, value);
  }

  return new Response(upstreamResponse.body, {
    status: upstreamResponse.status,
    statusText: upstreamResponse.statusText,
    headers,
  });
}

export async function POST(
  request: Request,
  { params }: { params: Promise<Params> },
): Promise<Response> {
  const { path } = await params;
  const upstreamPath = path.join("/");
  const upstreamUrl = new URL(`${API_BASE_URL}/${upstreamPath}`);
  const searchParams = new URL(request.url).searchParams;
  upstreamUrl.search = searchParams.toString();

  let upstreamResponse: Response;
  try {
    upstreamResponse = await fetch(upstreamUrl.toString(), {
      method: "POST",
      headers: {
        Accept: request.headers.get("accept") ?? "application/json",
        "Content-Type": request.headers.get("content-type") ?? "application/json",
      },
      body: await request.text(),
      cache: "no-store",
    });
  } catch {
    return Response.json(
      { error: "Failed to reach upstream API." },
      { status: 502 },
    );
  }

  const headers = new Headers();
  for (const name of RESPONSE_HEADER_ALLOWLIST) {
    const value = upstreamResponse.headers.get(name);
    if (value) headers.set(name, value);
  }

  return new Response(upstreamResponse.body, {
    status: upstreamResponse.status,
    statusText: upstreamResponse.statusText,
    headers,
  });
}
