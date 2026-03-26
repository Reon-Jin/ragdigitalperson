import { useEffect, useRef } from "react";
import { graphic, init, use } from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent } from "echarts/components";
import { SVGRenderer } from "echarts/renderers";

use([LineChart, GridComponent, SVGRenderer]);

type TrendTone = "rise" | "fall";

export function TrendMiniChart(props: { values: number[]; tone?: TrendTone }) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;

    const chart = init(element, undefined, { renderer: "svg" });
    const color = props.tone === "fall" ? "#00C087" : "#FF4D4F";

    if (!props.values.length) {
      chart.clear();
    } else {
      chart.setOption({
        animation: false,
        grid: { top: 8, right: 8, bottom: 8, left: 8 },
        xAxis: {
          type: "category",
          boundaryGap: false,
          show: false,
          data: props.values.map((_, index) => index),
        },
        yAxis: {
          type: "value",
          show: false,
          scale: true,
        },
        tooltip: { show: false },
        series: [
          {
            type: "line",
            data: props.values,
            smooth: true,
            symbol: "none",
            lineStyle: { width: 2, color },
            areaStyle: {
              color: new graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: `${color}55` },
                { offset: 1, color: `${color}08` },
              ]),
            },
          },
        ],
      });
    }

    const handleResize = () => chart.resize();
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      chart.dispose();
    };
  }, [props.tone, props.values]);

  return <div className="trend-mini-chart" ref={containerRef} />;
}
