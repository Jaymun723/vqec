// @ts-ignore
import Plotly from 'plotly.js-dist-min'
import createPlotlyComponent from 'react-plotly.js/factory.js'
import type { VisualizationTabState, ExperimentLayer } from '../types'
import { layerToGrid, computeRatioGrid, nanMin, nanMax, filterLayerData } from '../utils/math'
import { extractContourLines } from '../utils/contours'
import { useMemo, useState } from 'react'
import { useVisualizationStore } from '../store'

// Handle ESM/CJS interop for Vite
// @ts-ignore
const factory = (createPlotlyComponent.default || createPlotlyComponent) as any
const Plot = factory(Plotly)

interface PlotEngineProps {
  state: VisualizationTabState
}

export function PlotEngine({ state }: PlotEngineProps) {
  const { xAxisName, yAxisName, sliceValues, layers, comparisons, title: tabTitle } = state
  const { theme } = useVisualizationStore()

  const isDark = theme === 'dark'
  const textColor = isDark ? '#e6e8ee' : '#1f2937'
  const gridColor = isDark ? '#2a2f3a' : '#d1d5db'

  const [hoveredUid, setHoveredUid] = useState<string | null>(null)

  const cleanName = (name: string | null) => (name || '').replace(/_/g, ' ')

  // Apply hyperslice filtering to all visible layers
  const filteredLayers = useMemo(() => {
    if (!xAxisName) return []
    return (layers ?? [])
      .filter((l) => l.visible)
      .map(l => ({
        ...l,
        data: filterLayerData(l.data, sliceValues || {}, xAxisName, yAxisName)
      }))
  }, [layers, sliceValues, xAxisName, yAxisName])

  if (!xAxisName) {
    return <div className="viz-empty-msg">Please select an X axis to begin.</div>
  }

  const render1DPlot = () => {
    const data: any[] = []
    let minX = Infinity
    let maxX = -Infinity

    filteredLayers.forEach(layer => {
      const sortedData = [...layer.data].sort((a, b) => a.params[xAxisName] - b.params[xAxisName])
      const x = sortedData.map(d => d.params[xAxisName])
      const y = sortedData.map(d => d.lepr)
      
      minX = Math.min(minX, ...x)
      maxX = Math.max(maxX, ...x)

      data.push({
        x,
        y,
        type: 'scatter',
        mode: 'lines+markers',
        name: layer.experimentLabel,
        line: { color: layer.color },
        hovertemplate: `<b>${cleanName(xAxisName)}</b>: %{x}<br>LEPR: %{y}<extra></extra>`
      })
    })

    return (
      <Plot
        data={data}
        layout={{
          title: { text: tabTitle, font: { size: 16, color: textColor }, y: 0.98 },
          autosize: true,
          paper_bgcolor: 'rgba(0,0,0,0)',
          plot_bgcolor: 'rgba(0,0,0,0)',
          font: { color: textColor },
          hovermode: 'closest',
          xaxis: {
            title: { text: cleanName(xAxisName), font: { size: 14, color: textColor } },
            type: 'log',
            gridcolor: gridColor,
            automargin: true
          },
          yaxis: {
            title: { text: 'LEPR', font: { size: 14, color: textColor } },
            type: 'log',
            gridcolor: gridColor,
            automargin: true
          },
          margin: { l: 60, r: 40, b: 60, t: 40 },
          legend: {
            orientation: 'h',
            y: -0.2,
            x: 0.5,
            xanchor: 'center',
            bgcolor: 'rgba(0,0,0,0)'
          }
        }}
        useResizeHandler
        style={{ width: '100%', height: '100%' }}
      />
    )
  }

  const renderSingleHeatmap = (layer: ExperimentLayer) => {
    if (!yAxisName) {
      return <div className="viz-empty-msg">Y axis required for heatmap.</div>
    }

    const grid = layerToGrid(layer, xAxisName, yAxisName)

    const xMin = nanMin(grid.x)
    const xMax = nanMax(grid.x)
    const yMin = nanMin(grid.y)
    const yMax = nanMax(grid.y)

    const xRange = [Math.log10(xMin), Math.log10(xMax)]
    const yRange = [Math.log10(yMin), Math.log10(yMax)]

    const data: any[] = [
      {
        z: grid.z,
        x: grid.x,
        y: grid.y,
        type: 'heatmap',
        colorscale: 'Viridis',
        colorbar: {
          title: 'LEPR',
          titleside: 'right',
          x: 1.01,
          xpad: 0,
          len: 0.9
        },
        hovertemplate: `<b>${cleanName(xAxisName)}</b>: %{x}<br><b>${cleanName(yAxisName)}</b>: %{y}<br>LEPR: %{z}<extra></extra>`
      },
    ]

    return (
      <Plot
        data={data}
        layout={{
          title: { text: tabTitle, font: { size: 16, color: textColor }, y: 0.98 },
          autosize: true,
          paper_bgcolor: 'rgba(0,0,0,0)',
          plot_bgcolor: 'rgba(0,0,0,0)',
          font: { color: textColor },
          hovermode: 'closest',
          hoverdistance: 20,
          xaxis: {
            title: {
              text: cleanName(xAxisName),
              font: { size: 14, color: textColor }
            },
            type: 'log',
            gridcolor: gridColor,
            range: xRange,
            constrain: 'domain',
            automargin: true
          },
          yaxis: {
            title: {
              text: cleanName(yAxisName),
              font: { size: 14, color: textColor }
            },
            type: 'log',
            gridcolor: gridColor,
            scaleanchor: 'x',
            scaleratio: 1,
            range: yRange,
            constrain: 'domain',
            automargin: true
          },
          margin: { l: 20, r: 80, b: 20, t: 40 },
          showlegend: false
        }}


        useResizeHandler
        style={{ width: '100%', height: '100%' }}
      />
    )
  }

  const renderComparisonMode = () => {
    if (!yAxisName) return <div className="viz-empty-msg">Y axis required for comparison plots.</div>

    const data: any[] = []

    // Collect all unique X and Y values from all filtered layers to compute tight ranges
    const allXSet = new Set<number>()
    const allYSet = new Set<number>()
    filteredLayers.forEach(l => {
      l.data.forEach(d => {
        allXSet.add(d.params[xAxisName])
        allYSet.add(d.params[yAxisName])
      })
    })
    const allX = Array.from(allXSet).sort((a, b) => a - b)
    const allY = Array.from(allYSet).sort((a, b) => a - b)

    if (filteredLayers.length === 2) {
      const gridA = layerToGrid(filteredLayers[0], xAxisName, yAxisName)
      const gridB = layerToGrid(filteredLayers[1], xAxisName, yAxisName)
      const ratioGrid = computeRatioGrid(gridA, gridB, true)

      const flatZ = ratioGrid.z.flat()
      const zmin = nanMin(flatZ)
      const zmax = nanMax(flatZ)

      const Zclean = ratioGrid.z.map(row =>
        row.map(v => {
          if (v === null || isNaN(v)) {
            return v
          } else if (!Number.isFinite(v)) {
            return zmin
          } else {
            return v
          }
        })
      )

      const scale = (v: number) => (v - zmin) / (zmax - zmin);
      const zeroPos = scale(0);

      const colorscale = [
        [0.0, "blue"],
        [zeroPos, "white"],
        [1.0, "red"],
      ];

      data.push({
        type: "heatmap",
        z: Zclean,
        x: ratioGrid.x,
        y: ratioGrid.y,
        zmin,
        zmax,
        zmid: 0,
        colorscale,
        showscale: true,
        colorbar: {
          title: 'Log10 Ratio',
          titleside: 'right',
          x: 1.01,
          xpad: 0,
          len: 0.9
        },
        hovertemplate: `<b>${cleanName(xAxisName)}</b>: %{x}<br><b>${cleanName(yAxisName)}</b>: %{y}<br>Log10 Ratio: %{z}<extra></extra>`,
        showlegend: true,
        name: 'Ratio'
      })
    }

    // Add comparison contours
    (comparisons ?? []).forEach((comp, cIdx) => {
      if (!comp.visible) return
      const layerA = filteredLayers.find(l => l.id === comp.layerAId)
      const layerB = filteredLayers.find(l => l.id === comp.layerBId)
      if (!layerA || !layerB) return

      const gridA = layerToGrid(layerA, xAxisName, yAxisName)
      const gridB = layerToGrid(layerB, xAxisName, yAxisName)
      const ratioGrid = computeRatioGrid(gridA, gridB, false)

      comp.thresholds.forEach((t, tIdx) => {
        const paths = extractContourLines(ratioGrid, t)

        paths.forEach((path, pIdx) => {
          const uid = `contour-${cIdx}-${tIdx}-${pIdx}`
          const isHovered = hoveredUid === uid

          // Main line
          data.push({
            uid,
            x: path.x,
            y: path.y,
            type: 'scatter',
            mode: 'lines',
            line: {
              color: comp.color,
              width: 3,
              shape: 'spline',
              smoothing: 1.3
            },
            name: `${layerA.experimentLabel} / ${layerB.experimentLabel} = ${t}`,
            hovertemplate: `<b>Comparison</b>: ${layerA.experimentLabel} / ${layerB.experimentLabel}<br><b>Threshold</b>: ${t}<extra></extra>`,
            legendgroup: `group-${cIdx}-${tIdx}`,
            showlegend: pIdx === 0 // Only show in legend once
          })

          // Glow effect (underneath)
          if (isHovered) {
            data.push({
              x: path.x,
              y: path.y,
              type: 'scatter',
              mode: 'lines',
              hoverinfo: 'skip',
              line: {
                color: comp.color,
                width: 15,
                opacity: 0.3,
                shape: 'spline',
                smoothing: 1.3
              },
              legendgroup: `group-${cIdx}-${tIdx}`,
              showlegend: false
            })
          }
        })
      })
    })

    const xMin = nanMin(allX)
    const xMax = nanMax(allX)
    const yMin = nanMin(allY)
    const yMax = nanMax(allY)

    const xRange = [Math.log10(xMin), Math.log10(xMax)]
    const yRange = [Math.log10(yMin), Math.log10(yMax)]

    const isTwoLayer = filteredLayers.length === 2

    return (
      <Plot
        data={data}
        onHover={(e: any) => {
          const point = e.points[0]
          if (point.data.uid && (point.data.uid as string).startsWith('contour')) {
            setHoveredUid(point.data.uid)
          }
        }}
        onUnhover={() => setHoveredUid(null)}
        config={{
          // filename: tabTitle,
          toImageButtonOptions: { filename: tabTitle }

        }}
        layout={{
          title: { text: tabTitle, font: { size: 16, color: textColor }, y: 0.98 },
          autosize: true,
          paper_bgcolor: 'rgba(0,0,0,0)',
          plot_bgcolor: 'rgba(0,0,0,0)',
          font: { color: textColor },
          hovermode: 'closest',
          hoverdistance: 20,
          xaxis: {

            title: {
              text: cleanName(xAxisName),
              font: { size: 14, color: textColor }
            },

            type: 'log',
            gridcolor: gridColor,
            range: xRange,
            constrain: 'domain',
            automargin: true
          },
          yaxis: {
            title: {
              text: cleanName(yAxisName),
              font: { size: 14, color: textColor }
            },
            type: 'log',
            gridcolor: gridColor,
            scaleanchor: 'x',
            scaleratio: 1,
            range: yRange,
            constrain: 'domain',
            automargin: true
          },

          margin: { l: 20, r: isTwoLayer ? 180 : 100, b: 20, t: 40 },
          legend: {
            x: isTwoLayer ? 1.15 : 1.02,
            y: 1.0,
            xanchor: 'left',
            yanchor: 'top',
            bgcolor: 'rgba(0,0,0,0)',
            font: { size: 11 }
          },
          showlegend: true
        }}

        useResizeHandler
        style={{ width: '100%', height: '100%' }}
      />
    )
  }

  if (filteredLayers.length === 0) {
    return <div className="viz-empty-msg">No layers visible. Toggle visibility in the sidebar.</div>
  }

  if (!yAxisName) {
    return render1DPlot()
  }

  if (filteredLayers.length === 1) {
    return renderSingleHeatmap(filteredLayers[0])
  }

  return renderComparisonMode()
}
