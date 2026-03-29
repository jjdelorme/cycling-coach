import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js'

// Register core components
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Tooltip,
  Legend,
  Filler
)

// Highlight Plugin
const highlightPlugin = {
  id: 'highlightPlugin',
  afterDraw(chart: ChartJS) {
    const { ctx, chartArea, scales } = chart
    if (!chartArea || !scales.x) return

    // react-chartjs-2 often puts options in chart.config.options
    const options = chart.options?.plugins || (chart.config as any).options?.plugins
    const config = options?.highlightPlugin
    
    if (!config || !config.enabled) return

    const { target, map, highlightColor } = config
    if (target === undefined || target === null || target === -1 || !map || map.length === 0) return

    let firstIdx = -1, lastIdx = -1
    for (let i = 0; i < map.length; i++) {
      if (map[i] === target) {
        if (firstIdx === -1) firstIdx = i
        lastIdx = i
      }
    }

    if (firstIdx !== -1) {
      const x1 = scales.x.getPixelForValue(firstIdx)
      const x2 = scales.x.getPixelForValue(lastIdx)
      ctx.save()
      
      // Dim background
      ctx.fillStyle = 'rgba(0, 0, 0, 0.5)'
      if (x1 > chartArea.left) ctx.fillRect(chartArea.left, chartArea.top, x1 - chartArea.left, chartArea.bottom - chartArea.top)
      if (x2 < chartArea.right) ctx.fillRect(x2, chartArea.top, chartArea.right - x2, chartArea.bottom - chartArea.top)
      
      // Highlight segment
      ctx.strokeStyle = highlightColor || 'rgba(255, 255, 255, 0.5)'
      ctx.lineWidth = 3
      ctx.strokeRect(x1, chartArea.top, x2 - x1, chartArea.bottom - chartArea.top)
      ctx.restore()
    }
  }
}

ChartJS.register(highlightPlugin)

export { ChartJS }
