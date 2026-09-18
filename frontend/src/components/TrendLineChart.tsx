import React, { useState } from "react";
import { DailyTrendItem } from "../types";

interface Props {
  data: DailyTrendItem[];
  metric?: "posture" | "monitored";
}

export const TrendLineChart: React.FC<Props> = ({ data }) => {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  if (!data || data.length === 0) {
    return (
      <div className="chart-empty-state">
        <p>No trend data available for this range.</p>
      </div>
    );
  }

  const width = 640;
  const height = 240;
  const padding = { top: 20, right: 30, bottom: 40, left: 45 };
  const chartW = width - padding.left - padding.right;
  const chartH = height - padding.top - padding.bottom;

  // Filter or map data points
  const points = data.map((d, i) => {
    const x = padding.left + (i / Math.max(1, data.length - 1)) * chartW;
    const yVal = d.good_posture_percentage !== null ? d.good_posture_percentage : 0;
    const y = padding.top + chartH - (yVal / 100) * chartH;
    return { x, y, val: d.good_posture_percentage, date: d.date, raw: d };
  });

  const validPoints = points.filter((p) => p.val !== null);
  const pathD = validPoints.reduce((acc, p, idx) => {
    return `${acc} ${idx === 0 ? "M" : "L"} ${p.x} ${p.y}`;
  }, "");

  // Area fill under line
  const areaD =
    validPoints.length > 0
      ? `${pathD} L ${validPoints[validPoints.length - 1].x} ${
          padding.top + chartH
        } L ${validPoints[0].x} ${padding.top + chartH} Z`
      : "";

  return (
    <div className="trend-chart-container">
      <div className="chart-header-row">
        <span className="chart-legend-item">
          <span className="legend-swatch emerald"></span> Good Posture % (Observation Time)
        </span>
        <span className="chart-legend-item">
          <span className="legend-swatch rose"></span> Risk Events Count
        </span>
      </div>

      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="accessible-svg-chart"
        role="img"
        aria-label="Daily trend line chart showing good posture percentage and risk event counts"
      >
        <defs>
          <linearGradient id="postureGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#10b981" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#10b981" stopOpacity="0.0" />
          </linearGradient>
        </defs>

        {/* Grid lines */}
        {[0, 25, 50, 75, 100].map((pct) => {
          const y = padding.top + chartH - (pct / 100) * chartH;
          return (
            <g key={pct}>
              <line
                x1={padding.left}
                y1={y}
                x2={width - padding.right}
                y2={y}
                stroke="rgba(255, 255, 255, 0.08)"
                strokeDasharray="3 3"
              />
              <text
                x={padding.left - 8}
                y={y + 4}
                fill="#94a3b8"
                fontSize="10"
                textAnchor="end"
              >
                {pct}%
              </text>
            </g>
          );
        })}

        {/* Risk event bars */}
        {data.map((d, i) => {
          const x = padding.left + (i / Math.max(1, data.length - 1)) * chartW - 6;
          const maxEvents = Math.max(...data.map((item) => item.risk_event_count), 5);
          const barH = (d.risk_event_count / maxEvents) * (chartH * 0.4);
          const y = padding.top + chartH - barH;
          return (
            <rect
              key={`bar-${d.date}`}
              x={x}
              y={y}
              width={12}
              height={barH}
              fill="rgba(244, 63, 94, 0.25)"
              rx={2}
            />
          );
        })}

        {/* Area fill & Path */}
        {areaD && <path d={areaD} fill="url(#postureGrad)" />}
        {pathD && (
          <path
            d={pathD}
            fill="none"
            stroke="#10b981"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        )}

        {/* Data points */}
        {points.map((p, idx) => (
          <g key={p.date} onMouseEnter={() => setHoveredIdx(idx)} onMouseLeave={() => setHoveredIdx(null)}>
            <circle
              cx={p.x}
              cy={p.val !== null ? p.y : padding.top + chartH}
              r={hoveredIdx === idx ? 6 : 3.5}
              fill={p.val !== null ? "#10b981" : "#475569"}
              stroke="#0f172a"
              strokeWidth="2"
              cursor="pointer"
            />
            {/* X-axis labels (every 2nd or 3rd day if dense) */}
            {(data.length <= 14 || idx % 2 === 0) && (
              <text
                x={p.x}
                y={height - 12}
                fill="#94a3b8"
                fontSize="9"
                textAnchor="middle"
              >
                {p.date.slice(5)}
              </text>
            )}
          </g>
        ))}

        {/* Tooltip */}
        {hoveredIdx !== null && (
          <g transform={`translate(${points[hoveredIdx].x}, ${Math.max(30, points[hoveredIdx].y - 25)})`}>
            <rect
              x="-60"
              y="-25"
              width="120"
              height="30"
              fill="#1e293b"
              stroke="#334155"
              rx="4"
              filter="drop-shadow(0 4px 6px rgba(0,0,0,0.5))"
            />
            <text x="0" y="-14" fill="#f8fafc" fontSize="10" fontWeight="bold" textAnchor="middle">
              {points[hoveredIdx].date}
            </text>
            <text x="0" y="-2" fill="#10b981" fontSize="9" textAnchor="middle">
              {points[hoveredIdx].val !== null ? `${points[hoveredIdx].val}% posture` : "No valid exposure"}
              {` • ${points[hoveredIdx].raw.risk_event_count} events`}
            </text>
          </g>
        )}
      </svg>
    </div>
  );
};
