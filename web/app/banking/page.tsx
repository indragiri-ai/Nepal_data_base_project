import type { Metadata } from "next";
import BankingDashboard from "@/components/BankingDashboard";

export const metadata: Metadata = {
  title: "Banking & finance",
  description:
    "Nepal's banking system month by month — credit, deposits, liquidity, capital, interest rates, and financial access, from Nepal Rastra Bank's Banking and Financial Statistics.",
};

export default function BankingPage() {
  return <BankingDashboard />;
}
