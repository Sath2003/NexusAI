"use client";

import React, { useMemo } from "react";
import { Excalidraw } from "@excalidraw/excalidraw";

interface ExcalidrawBoardProps {
  elements: any[];
  appState?: any;
}

/**
 * Normalizes Excalidraw elements from the LLM to prevent glyph rendering bugs.
 * - Forces fontFamily=3 (Cascadia Code) on all text elements.
 *   fontFamily 1 (Virgil) maps text content to Unicode icon glyphs which renders
 *   as lock icons / person icons instead of readable text.
 * - Forces roughness=0 for clean, professional-looking shapes.
 */
function normalizeElements(elements: any[]): any[] {
  if (!Array.isArray(elements)) return [];
  return elements.map((el) => {
    const normalized = { ...el };
    // Fix font family on text elements — 3 = Cascadia Code (plain readable text)
    if (el.type === "text" || el.fontFamily !== undefined) {
      normalized.fontFamily = 3;
    }
    // Remove roughness hand-drawn effect for professional look
    if (el.roughness !== undefined) {
      normalized.roughness = 0;
    }
    // Ensure strokeWidth is always visible
    if (el.strokeWidth === undefined || el.strokeWidth === 0) {
      normalized.strokeWidth = 2;
    }
    // Remove any image type elements which cause rendering errors
    if (el.type === "image") {
      return null;
    }
    return normalized;
  }).filter(Boolean);
}

export default function ExcalidrawBoard({ elements, appState }: ExcalidrawBoardProps) {
  const normalizedElements = useMemo(() => normalizeElements(elements), [elements]);

  return (
    <div className="w-full h-[480px] border border-white/10 rounded-xl overflow-hidden bg-[#0d1117] my-3 relative">
      <Excalidraw
        initialData={{
          elements: normalizedElements,
          appState: {
            viewBackgroundColor: "#0d1117",
            currentItemFontFamily: 3, // Cascadia Code — plain text, not icon glyphs
            theme: "dark",
            collaborative: false,
            gridSize: null,
            ...appState
          },
          scrollToContent: true
        }}
        detectScroll={true}
      />
    </div>
  );
}
