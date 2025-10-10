export const runtime = "nodejs"; // ensure Node runtime

import { NextResponse } from "next/server";

// Map /api/insights?client=masplus -> NOTION_DB_MASPLUS
function dbIdForSlug(slug: string) {
  const key = `NOTION_DB_${slug.toUpperCase()}` as keyof NodeJS.ProcessEnv;
  const id = process.env[key];
  if (!id) throw new Error(`Unknown client slug or DB not configured: ${slug}`);
  return id;
}

export async function GET(req: Request) {
  try {
    const { searchParams } = new URL(req.url);
    const slug = searchParams.get("client") || "masplus";
    const database_id = dbIdForSlug(slug);

    // POST /v1/databases/{database_id}/query
    const notionRes = await fetch(`https://api.notion.com/v1/databases/${database_id}/query`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${process.env.NOTION_TOKEN}`,
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        sorts: [{ property: "Date", direction: "descending" }],
        // You can comment this filter out temporarily to see everything:
        filter: { property: "Status", select: { equals: "Published" } },
      }),
    });

    if (!notionRes.ok) {
      const text = await notionRes.text();
      return NextResponse.json({ error: `Notion error ${notionRes.status}: ${text}` }, { status: 500 });
    }

    const data = await notionRes.json();
    // Notion returns { results: [...] }
    return NextResponse.json(data.results);
  } catch (e: any) {
    return NextResponse.json({ error: e.message || String(e) }, { status: 400 });
  }
}
