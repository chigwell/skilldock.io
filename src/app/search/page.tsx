import Navigation from "@/components/navigation";
import SearchResultsView from "@/components/search/search-results-view";
import SiteFooter from "@/components/site-footer";
import { Suspense } from "react";

export default function SearchPage() {
  return (
    <main className="relative min-h-screen">
      <Navigation />
      <Suspense fallback={<section className="min-h-[60vh]" />}>
        <SearchResultsView />
      </Suspense>
      <SiteFooter />
    </main>
  );
}
