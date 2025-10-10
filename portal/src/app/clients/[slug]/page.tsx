async function getInsights(slug: string) {
  const base =
    process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : "http://localhost:3000";
  const res = await fetch(`${base}/api/insights?client=${slug}`, { cache: "no-store" });
  if (!res.ok) return [];
  return res.json();
}

export default async function ClientPage({ params }: { params: { slug: string } }) {
  const items = await getInsights(params.slug);

  return (
    <main className="p-6 max-w-5xl mx-auto">
      <h1 className="text-2xl font-semibold">Insights — {params.slug.toUpperCase()}</h1>

      <div className="mt-6 grid gap-4 md:grid-cols-2">
        {items.map((it: any) => {
          const p = it.properties || {};
          const title =
          p["Title"]?.title?.[0]?.plain_text ||
          p["Headline"]?.rich_text?.[0]?.plain_text ||
          "Untitled";
          const detail = p["Detail"]?.rich_text?.[0]?.plain_text || "";
          const metric =
            p["Metric"]?.rich_text?.[0]?.plain_text ??
            (typeof p["Metric"]?.number === "number" ? String(p["Metric"].number) : "");
          const label = p["Metric Label"]?.rich_text?.[0]?.plain_text || "";
          const type = p["Insight Type"]?.select?.name || "";
          const date = p["Date"]?.date?.start
            ? new Date(p["Date"].date.start).toLocaleDateString()
            : "";

          return (
            <article key={it.id} className="rounded-2xl border p-4 shadow-sm">
              <div className="text-xs opacity-70">{date}</div>
              <h2 className="text-lg font-bold mt-1">{title}</h2>
              {type ? (
                <div className="mt-1 text-xs px-2 py-0.5 border rounded-full w-fit">{type}</div>
              ) : null}
              <p className="mt-3 text-sm opacity-90">{detail}</p>
              <div className="mt-3 text-sm">
                {metric ? <span className="font-semibold">{metric}</span> : null}
                {label ? <span className="opacity-70 ml-1">{label}</span> : null}
              </div>
            </article>
          );
        })}
      </div>

      {!items.length && (
        <p className="mt-8 text-sm opacity-70">
          No published insights yet. Set <em>Status</em> = <strong>Published</strong> for a row in
          Notion and refresh.
        </p>
      )}
    </main>
  );
}
