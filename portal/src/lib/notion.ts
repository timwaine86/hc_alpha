import { Client } from "@notionhq/client";

export const notion = new Client({ auth: process.env.NOTION_TOKEN });

export function dbIdForSlug(slug: string) {
  const key = `NOTION_DB_${slug.toUpperCase()}` as keyof NodeJS.ProcessEnv;
  const id = process.env[key];
  if (!id) throw new Error(`Unknown client slug or DB not configured: ${slug}`);
  return id;
}
