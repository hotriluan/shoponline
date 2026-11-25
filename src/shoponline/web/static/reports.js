/* Report charts. Data is embedded in the page as JSON (#chart-data); no request is made. */
(function () {
  'use strict';
  // The validated categorical order (blue, orange, aqua, yellow, magenta, green, violet, red).
  var SERIES = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'];
  var money = function (v) { return v === null || v === undefined ? '' : Number(v).toLocaleString('vi-VN') + ' đ'; };
  var compact = function (v) {
    var a = Math.abs(v);
    if (a >= 1e9) return (v / 1e9).toLocaleString('vi-VN') + ' tỷ';
    if (a >= 1e6) return (v / 1e6).toLocaleString('vi-VN') + ' tr';
    return Number(v).toLocaleString('vi-VN');
  };

  function baseOptions() {
    return {
      responsive: true,
      animation: false,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { position: 'bottom', labels: { usePointStyle: true, boxWidth: 8 } },
        tooltip: { callbacks: { label: function (c) { return c.dataset.label + ': ' + money(c.parsed.y); } } }
      },
      scales: {
        x: { grid: { display: false } },
        y: { beginAtZero: true, ticks: { callback: compact }, grid: { color: '#e8eef4' } }
      }
    };
  }

  function lines(canvas, d) {
    var defs = [['Giá trị trên sàn', d.marketplace], ['Doanh thu hóa đơn', d.invoice], ['Tiền thực nhận', d.settled]];
    new Chart(canvas, {
      type: 'line',
      data: {
        labels: d.labels,
        datasets: defs.map(function (def, i) {
          return {
            label: def[0], data: def[1], borderColor: SERIES[i], backgroundColor: SERIES[i],
            borderWidth: 2, pointRadius: 4, pointHoverRadius: 6, pointBackgroundColor: SERIES[i],
            pointBorderColor: '#ffffff', pointBorderWidth: 2, spanGaps: false, tension: 0
          };
        })
      },
      options: baseOptions()
    });
  }

  function stack(canvas, d) {
    var options = baseOptions();
    options.scales.x.stacked = true;
    options.scales.y.stacked = true;
    new Chart(canvas, {
      type: 'bar',
      data: {
        labels: d.labels,
        datasets: d.series.map(function (s, i) {
          var colour = SERIES[i % SERIES.length];
          return { label: s.name, data: s.data, backgroundColor: colour, borderColor: '#ffffff', borderWidth: 2, borderRadius: 3 };
        })
      },
      options: options
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    var holder = document.getElementById('chart-data');
    var canvas = document.querySelector('canvas[data-chart]');
    if (!holder || !canvas || typeof Chart === 'undefined') return;
    var data = JSON.parse(holder.textContent);
    ({ lines: lines, stack: stack })[canvas.dataset.chart](canvas, data);
  });
})();
