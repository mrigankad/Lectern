"use client";

import { useParams, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { MediaStudio } from "@/components/media/MediaStudio";

function MediaPageInner() {
  const { id } = useParams<{ id: string }>();
  const params = useSearchParams();
  return <MediaStudio key={id} deckId={id} slideId={params.get("slide")} />;
}

export default function DeckMediaPage() {
  return (
    <Suspense fallback={null}>
      <MediaPageInner />
    </Suspense>
  );
}
