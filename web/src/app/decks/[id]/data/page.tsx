"use client";

import { useParams, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { DataStudio } from "@/components/sources/DataStudio";

function DataPageInner() {
  const { id } = useParams<{ id: string }>();
  const params = useSearchParams();
  const slide = params.get("slide");
  return <DataStudio key={`${id}-${slide ?? ""}`} deckId={id} slideId={slide} />;
}

export default function DeckDataPage() {
  return (
    <Suspense fallback={null}>
      <DataPageInner />
    </Suspense>
  );
}
