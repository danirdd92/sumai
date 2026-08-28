import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const postsCollection = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/posts" }),
  schema: z.object({
    title: z.string(),
    publishDate: z.coerce.date(),
    originalUrl: z.string().url(),
    source: z.string(),
    tags: z.array(z.string()),
    summary: z.string().optional(),
  }),
});

export const collections = {
  'posts': postsCollection,
};
