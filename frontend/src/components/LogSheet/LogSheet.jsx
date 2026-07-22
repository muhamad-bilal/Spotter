import {
  GRID_BOTTOM,
  GRID_TOP,
  GRID_W,
  GRID_X,
  HEIGHT,
  LABEL_PAD_LEFT,
  LABEL_W,
  REMARK_ANGLE,
  REMARKS_H,
  ROW_H,
  ROWS,
  TOTALS_W,
  WIDTH,
  buildRemarks,
  buildTrace,
  hourTicks,
  minuteToX,
  quarterTicks,
  remarkAnchorDepth,
  rowTop,
  rowY,
  totalOfDisplayed,
  totalsForDisplay,
  truncateRemark,
} from '../../lib/logGrid.js'
import './LogSheet.css'

function formatDate(iso) {
  const date = new Date(`${iso}T00:00:00`)
  if (Number.isNaN(date.getTime())) return iso
  return new Intl.DateTimeFormat('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(date)
}

export default function LogSheet({ day, index, count }) {
  const { lines, connectors } = buildTrace(day.segments)
  const remarks = buildRemarks(day.segments)
  const totals = totalsForDisplay(day.totals)
  const grandTotal = totalOfDisplayed(day.totals)
  const hours = hourTicks()
  const quarters = quarterTicks()

  return (
    <article className="sheet">
      <header className="sheet__header">
        <div>
          <p className="eyebrow">
            Day {index + 1} of {count}
          </p>
          <h3 className="sheet__date">{formatDate(day.date)}</h3>
        </div>
        <dl className="sheet__meta">
          <div>
            <dt>Miles driving</dt>
            <dd className="tnum">{Number(day.total_miles ?? 0).toLocaleString('en-US')}</dd>
          </div>
          <div>
            <dt>Total</dt>
            <dd className="tnum">{grandTotal.toFixed(2)} hrs</dd>
          </div>
        </dl>
      </header>

      <div className="sheet__scroll">
        <svg
          className="sheet__svg"
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          role="img"
          aria-label={`Duty status log for ${formatDate(day.date)}`}
        >
          {/* --- hour labels across the top ---
              The closing midnight is deliberately unlabelled: it would collide
              with the totals-column caption, and the grid ending at midnight is
              self-evident from the one at the start. */}
          {hours.map(({ hour, x, label, isMajor }) =>
            hour === 24 ? null : (
              <text
                key={`hl-${hour}`}
                className={`sheet__hour${isMajor ? ' sheet__hour--major' : ''}`}
                x={x}
                y={GRID_TOP - 14}
                textAnchor="middle"
              >
                {label}
              </text>
            ),
          )}

          {/* --- row bands --- */}
          {ROWS.map((row, rowIndex) => (
            <g key={row.status}>
              <rect
                className={`sheet__band${rowIndex % 2 ? ' sheet__band--alt' : ''}`}
                x={GRID_X}
                y={rowTop(rowIndex)}
                width={GRID_W}
                height={ROW_H}
              />
              <text className="sheet__row-number" x={LABEL_PAD_LEFT} y={rowY(row.status) + 4}>
                {row.short}
              </text>
              <text
                className="sheet__row-label"
                x={LABEL_W - 14}
                y={rowY(row.status) + 4}
                textAnchor="end"
              >
                {row.label}
              </text>
            </g>
          ))}

          {/* --- 15-minute ticks, rising from each band's floor --- */}
          {ROWS.map((row, rowIndex) =>
            quarters.map(({ x, height }, tickIndex) => (
              <line
                key={`q-${rowIndex}-${tickIndex}`}
                className="sheet__tick"
                x1={x}
                x2={x}
                y1={rowTop(rowIndex) + ROW_H}
                y2={rowTop(rowIndex) + ROW_H - height}
              />
            )),
          )}

          {/* --- hour lines, full height --- */}
          {hours.map(({ hour, x, isMajor }) => (
            <line
              key={`h-${hour}`}
              className={`sheet__hour-line${isMajor ? ' sheet__hour-line--major' : ''}`}
              x1={x}
              x2={x}
              y1={GRID_TOP}
              y2={GRID_BOTTOM}
            />
          ))}

          {/* --- row separators --- */}
          {[0, 1, 2, 3, 4].map((rowIndex) => (
            <line
              key={`sep-${rowIndex}`}
              className="sheet__rule"
              x1={GRID_X}
              x2={GRID_X + GRID_W}
              y1={GRID_TOP + rowIndex * ROW_H}
              y2={GRID_TOP + rowIndex * ROW_H}
            />
          ))}

          {/* --- the trace: verticals first so the horizontals sit on top --- */}
          {connectors.map((connector, i) => (
            <line
              key={`c-${i}`}
              className="sheet__connector"
              x1={connector.x}
              x2={connector.x}
              y1={connector.y1}
              y2={connector.y2}
            />
          ))}
          {lines.map((line, i) => (
            <line
              key={`s-${i}`}
              className={`sheet__segment sheet__segment--${line.status}`}
              data-status={line.status}
              data-start={line.startMinute}
              data-end={line.endMinute}
              x1={line.x1}
              x2={line.x2}
              y1={line.y}
              y2={line.y}
            />
          ))}

          {/* --- totals column --- */}
          <line
            className="sheet__rule"
            x1={GRID_X + GRID_W}
            x2={GRID_X + GRID_W}
            y1={GRID_TOP}
            y2={GRID_BOTTOM}
          />
          {totals.map((total, rowIndex) => (
            <text
              key={`t-${total.status}`}
              className={`sheet__total sheet__total--${total.status}`}
              data-status={total.status}
              x={GRID_X + GRID_W + TOTALS_W / 2}
              y={rowY(total.status) + 4}
              textAnchor="middle"
            >
              {total.text}
            </text>
          ))}
          <text
            className="sheet__totals-caption"
            x={GRID_X + GRID_W + TOTALS_W / 2}
            y={GRID_TOP - 14}
            textAnchor="middle"
          >
            Hours
          </text>
          <line
            className="sheet__rule"
            x1={GRID_X + GRID_W}
            x2={WIDTH}
            y1={GRID_BOTTOM}
            y2={GRID_BOTTOM}
          />
          <text
            className="sheet__grand-total tnum"
            data-testid="grand-total"
            x={GRID_X + GRID_W + TOTALS_W / 2}
            y={GRID_BOTTOM + 18}
            textAnchor="middle"
          >
            {grandTotal.toFixed(2)}
          </text>

          {/* --- remarks strip --- */}
          {/* Caption sits in the left label column, under the row captions,
              rather than indented at the grid's start. */}
          <text className="sheet__remarks-caption" x={LABEL_PAD_LEFT} y={GRID_BOTTOM + 18}>
            Remarks
          </text>
          {remarks.map((remark, i) => {
            const anchorY = GRID_BOTTOM + remarkAnchorDepth(remark.text)
            return (
              <g key={`r-${i}`}>
                <line
                  className="sheet__remark-stem"
                  x1={remark.x}
                  x2={remark.x}
                  y1={GRID_BOTTOM}
                  y2={anchorY}
                />
                <text
                  className="sheet__remark"
                  x={remark.x}
                  y={anchorY}
                  transform={`rotate(${-REMARK_ANGLE}, ${remark.x}, ${anchorY})`}
                >
                  {truncateRemark(remark.text)}
                </text>
              </g>
            )
          })}
          <line
            className="sheet__rule"
            x1={GRID_X}
            x2={GRID_X + GRID_W}
            y1={GRID_BOTTOM + REMARKS_H}
            y2={GRID_BOTTOM + REMARKS_H}
          />
        </svg>
      </div>
    </article>
  )
}
