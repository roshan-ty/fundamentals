/**
 * Bulls & Bears Fundamentals — Chart.js Configuration Helpers
 * Provides reusable Chart.js chart configurations for FRED data, CFTC data, etc.
 */

// ── Global defaults ──────────────────────────────────────────────────────────

Chart.defaults.font.family = "'Segoe UI', system-ui, sans-serif";
Chart.defaults.font.size = 11;
Chart.defaults.color = '#495057';
Chart.defaults.borderColor = '#dee2e6';

function updateChartTheme(charts) {
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  const textColor = isDark ? '#ffffff' : '#495057';
  const gridColor = isDark ? '#333333' : '#dee2e6';
  
  charts.forEach(chart => {
    if (!chart) return;
    chart.options.plugins.legend.labels.color = textColor;
    chart.options.scales.x.ticks.color = textColor;
    chart.options.scales.y.ticks.color = textColor;
    chart.options.scales.x.grid.color = gridColor;
    chart.options.scales.y.grid.color = gridColor;
    chart.update('none');
  });
}

// ── FRED historical line chart ───────────────────────────────────────────────

function createFredChart(canvasId, seriesId, data, seriesName) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return null;

  // Filter data for this series
  const seriesData = data.series
    .filter(s => s.series_id === seriesId)
    .sort((a, b) => a.date.localeCompare(b.date));

  if (seriesData.length === 0) return null;

  const labels = seriesData.map(s => s.date);
  const values = seriesData.map(s => s.value);
  const unit = seriesData[0]?.unit || '';

  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  const textColor = isDark ? '#ffffff' : '#495057';
  const gridColor = isDark ? '#333333' : '#dee2e6';

  // Determine trend color
  const firstVal = values[0];
  const lastVal = values[values.length - 1];
  const trendUp = lastVal >= firstVal;
  const lineColor = trendUp ? '#198754' : '#dc3545';
  const fillColor = trendUp ? 'rgba(25,135,84,0.1)' : 'rgba(220,53,69,0.1)';

  const chart = new Chart(canvas, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [{
        label: seriesName,
        data: values,
        borderColor: lineColor,
        backgroundColor: fillColor,
        borderWidth: 2,
        fill: true,
        tension: 0.3,
        pointRadius: 2,
        pointHoverRadius: 5,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: true,
          labels: { color: textColor, font: { size: 11 } }
        },
        tooltip: {
          callbacks: {
            label: function(ctx) {
              let val = ctx.parsed.y;
              if (Number.isInteger(val)) return `${val.toLocaleString()} ${unit}`;
              return `${val.toFixed(2)} ${unit}`;
            }
          }
        }
      },
      scales: {
        x: {
          ticks: { color: textColor, font: { size: 10 }, maxTicksLimit: 12 },
          grid: { color: gridColor }
        },
        y: {
          ticks: { color: textColor, font: { size: 10 } },
          grid: { color: gridColor },
          beginAtZero: seriesId === 'UNRATE' || seriesId === 'FEDFUNDS'
        }
      }
    }
  });

  return chart;
}

// ── CFTC net positions bar chart ─────────────────────────────────────────────

function createCftcChart(canvasId, data) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || !data.positions || data.positions.length === 0) return null;

  const labels = data.positions.map(p => p.market);
  const netPositions = data.positions.map(p => p.net_speculative);
  const percentiles = data.positions.map(p => p.percentile_52w);

  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  const textColor = isDark ? '#ffffff' : '#495057';
  const gridColor = isDark ? '#333333' : '#dee2e6';

  const barColors = netPositions.map(v => v >= 0 ? '#198754' : '#dc3545');

  const chart = new Chart(canvas, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Net Speculative Position',
          data: netPositions,
          backgroundColor: barColors,
          borderColor: barColors,
          borderWidth: 1,
          yAxisID: 'y',
        },
        {
          label: '52-Week Percentile',
          data: percentiles,
          type: 'line',
          borderColor: '#0d6efd',
          backgroundColor: 'rgba(13,110,253,0.1)',
          borderWidth: 2,
          pointRadius: 4,
          pointBackgroundColor: '#0d6efd',
          yAxisID: 'y1',
          tension: 0.3,
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: { color: textColor, font: { size: 10 } }
        },
        tooltip: {
          callbacks: {
            label: function(ctx) {
              if (ctx.dataset.yAxisID === 'y') {
                return `Net: ${ctx.parsed.y.toLocaleString()}`;
              }
              return `Percentile: ${ctx.parsed.y.toFixed(1)}%`;
            }
          }
        }
      },
      scales: {
        x: {
          ticks: { color: textColor, font: { size: 10 } },
          grid: { color: gridColor }
        },
        y: {
          position: 'left',
          ticks: { color: textColor, font: { size: 10 } },
          grid: { color: gridColor },
          title: {
            display: true,
            text: 'Net Contracts',
            color: textColor,
          }
        },
        y1: {
          position: 'right',
          min: 0,
          max: 100,
          ticks: { color: textColor, font: { size: 10 }, callback: v => v + '%' },
          grid: { display: false },
          title: {
            display: true,
            text: 'Percentile',
            color: textColor,
          }
        }
      }
    }
  });

  return chart;
}

// ── Yield comparison chart ───────────────────────────────────────────────────

function createYieldChart(canvasId, data) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || !data.entries || data.entries.length === 0) return null;

  const labels = data.entries.map(e => e.instrument);
  const yields = data.entries.map(e => e.yield_value);
  const ma50 = data.entries.map(e => e.yield_ma50);

  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  const textColor = isDark ? '#ffffff' : '#495057';
  const gridColor = isDark ? '#333333' : '#dee2e6';

  const chart = new Chart(canvas, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Current Yield',
          data: yields,
          backgroundColor: 'rgba(13,110,253,0.7)',
          borderColor: '#0d6efd',
          borderWidth: 1,
        },
        {
          label: '50-Day MA',
          data: ma50.map(v => v || null),
          type: 'line',
          borderColor: '#fd7e14',
          backgroundColor: 'rgba(253,126,20,0.1)',
          borderWidth: 2,
          pointRadius: 4,
          pointBackgroundColor: '#fd7e14',
          tension: 0.3,
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: { color: textColor, font: { size: 10 } }
        }
      },
      scales: {
        x: {
          ticks: { color: textColor, font: { size: 10 } },
          grid: { color: gridColor }
        },
        y: {
          ticks: { color: textColor, font: { size: 10 }, callback: v => v + '%' },
          grid: { color: gridColor },
          title: {
            display: true,
            text: 'Yield (%)',
            color: textColor,
          }
        }
      }
    }
  });

  return chart;
}

// ── USD gauge chart ──────────────────────────────────────────────────────────

function createGaugeChart(canvasId, score) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return null;

  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  const textColor = isDark ? '#ffffff' : '#495057';

  // Determine color based on score
  let color;
  if (score >= 8) color = '#198754';
  else if (score >= 6) color = '#0d6efd';
  else if (score >= 4) color = '#ffc107';
  else if (score >= 2) color = '#fd7e14';
  else color = '#dc3545';

  const chart = new Chart(canvas, {
    type: 'doughnut',
    data: {
      datasets: [{
        data: [score, 10 - score],
        backgroundColor: [color, isDark ? '#333' : '#e9ecef'],
        borderWidth: 0,
        circumference: 270,
        rotation: 135,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '75%',
      plugins: {
        legend: { display: false },
        tooltip: { enabled: false }
      }
    },
    plugins: [{
      id: 'centerText',
      beforeDraw: function(chart) {
        const {width, height, ctx} = chart;
        ctx.save();
        const text = score.toFixed(1);
        ctx.font = 'bold 36px "Segoe UI", sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillStyle = textColor;
        ctx.fillText(text, width / 2, height / 2 + 5);
        ctx.restore();
      }
    }]
  });

  return chart;
}