import { type NodeProps } from "@xyflow/react";
import { LANE_HEIGHT, LANE_WIDTH } from "../state/graphStore";

export interface LaneNodeData {
  label: string;
  index: number;
  color: string;
  [key: string]: unknown;
}

// A non-interactive group frame marking one network tier, ComfyUI-style: a tinted
// border with a title tab in the corner. Agent nodes sit inside it; dragging a
// node into another frame reassigns its tier.
export function LaneNode({ data }: NodeProps) {
  const d = data as LaneNodeData;
  return (
    <div
      className="lane-frame"
      style={{
        width: LANE_WIDTH,
        height: LANE_HEIGHT,
        border: `1px solid ${d.color}44`,
        background: `${d.color}0a`,
      }}
    >
      <div className="lane-tab" style={{ color: d.color, borderColor: `${d.color}66` }}>
        {d.label}
      </div>
    </div>
  );
}
