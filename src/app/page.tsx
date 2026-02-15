import CircuitFlow from "@/components/hero/circuit-flow";
import Navigation from "@/components/navigation";
import OnePromptSection from "@/components/one-prompt-section";
import RegistryOverviewSection from "@/components/registry-overview-section";
import SiteFooter from "@/components/site-footer";

export default function Home() {
  return (
    <main className="relative min-h-screen">
      <Navigation />
      <CircuitFlow />
      <RegistryOverviewSection />
      <OnePromptSection />
      <SiteFooter />
    </main>
  );
}
