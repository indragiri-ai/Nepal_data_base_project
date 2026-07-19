import type { Metadata } from "next";
import PopulationDashboard from "@/components/PopulationDashboard";

export const metadata: Metadata = {
  title: "Population & census",
  description:
    "Census 2021 on the map of Nepal — population, density, sex ratio, growth, and literacy for every province and district, from the National Statistics Office.",
};

export default function PopulationPage() {
  return <PopulationDashboard />;
}
