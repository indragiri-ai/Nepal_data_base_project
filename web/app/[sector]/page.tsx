import type { Metadata } from "next";
import { notFound } from "next/navigation";
import SectorDashboard from "@/components/SectorDashboard";
import { SECTORS } from "@/lib/sectors";

// The 8 sector routes are known at build time; anything else 404s. Static
// routes (/explore, /banking, /population) take precedence over this dynamic
// segment, so there is no collision.
export function generateStaticParams(): { sector: string }[] {
  return SECTORS.map((s) => ({ sector: s.slug }));
}
export const dynamicParams = false;

interface Props {
  params: { sector: string };
}

export function generateMetadata({ params }: Props): Metadata {
  const sector = SECTORS.find((s) => s.slug === params.sector);
  if (!sector) return {};
  return { title: sector.title, description: sector.description };
}

export default function SectorPage({ params }: Props) {
  const sector = SECTORS.find((s) => s.slug === params.sector);
  if (!sector) notFound();
  return <SectorDashboard slug={sector.slug} />;
}
