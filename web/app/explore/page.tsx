import type { Metadata } from "next";
import ExploreDashboard from "@/components/ExploreDashboard";

export const metadata: Metadata = {
  title: "Explore indicators",
  description:
    "Six decades of annual indicators for Nepal — economy, health, education, trade — charted with the source behind every number.",
};

export default function ExplorePage() {
  return <ExploreDashboard />;
}
