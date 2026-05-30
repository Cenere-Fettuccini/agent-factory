import { type NodeProps } from "@xyflow/react";
import { LANE_HEIGHT, LANE_WIDTH } from "../state/graphStore";

export interface LaneNodeData {
  label: string;
  index: number;
  [key: string]: unknown;
}

// A non-interactive background band marking one network tier. Agent nodes sit
// inside it; dragging a node into another band reassigns its tier.
export function LaneNode({ data }: NodeProps) {
  const d = data as LaneNodeData;
  return (
    <div
      style={{
        width: LANE_WIDTH,
        height: LANE_HEIGHT,
        border: "1px dashed var(--border)",
        borderRadius: 12,
        background: d.index % 2 === 0 ? "rgba(255,255,255,0.015)" : "transparent",
      }}
    >
      <div className="lane-label">{d.label}</div>
    </div>
  );
}
