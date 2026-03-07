import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) {
    return null;
  }

  const value = payload[0]?.value;
  return (
    <div className="rounded-sm border border-border bg-background/95 p-2 text-xs" data-testid="pattern-chart-tooltip">
      <p className="font-mono text-muted-foreground">{label}</p>
      <p className="font-mono text-foreground">Kapanış: {value}</p>
    </div>
  );
};

const breakoutBadgeClass = (pattern) => {
  if (!pattern.confirmed) {
    return "border-border bg-muted/20 text-muted-foreground";
  }
  return pattern.direction === "bullish"
    ? "border-primary/50 bg-primary/15 text-primary"
    : "border-destructive/50 bg-destructive/15 text-destructive";
};

export const PatternChartPanel = ({ signal }) => {
  if (!signal) {
    return (
      <Card className="border-border/70 bg-card/45" data-testid="pattern-chart-empty-card">
        <CardContent className="p-8 text-muted-foreground" data-testid="pattern-chart-empty-text">
          Grafik ve formasyon detayını görmek için soldan bir hisse seçin.
        </CardContent>
      </Card>
    );
  }

  const chartData = signal.price_history || [];
  const patternPointDates = new Set(signal.patterns?.flatMap((pattern) => pattern.points || []) || []);
  const patternMarkers = chartData
    .filter((row) => patternPointDates.has(row.date))
    .map((row) => ({ date: row.date, close: row.close }));

  const breakdown = signal.score_breakdown || {};

  return (
    <div className="space-y-4" data-testid="pattern-chart-panel">
      <Card className="border-border/70 bg-card/45 backdrop-blur-md" data-testid="pattern-visualization-card">
        <CardHeader className="border-b border-border/60 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <CardTitle className="text-lg font-bold" data-testid="pattern-chart-title">
              Formasyon Grafiği · {signal.symbol}
            </CardTitle>
            <Badge className="rounded-sm border border-primary/40 bg-primary/15 text-primary" data-testid="pattern-chart-score-badge">
              Skor: {signal.bullish_score}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="p-4">
          <div className="h-[380px] w-full" data-testid="pattern-visual-chart">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 4, left: -20 }}>
                <CartesianGrid stroke="rgba(255,255,255,0.08)" strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fill: "#a1a1aa", fontSize: 10 }} minTickGap={35} />
                <YAxis tick={{ fill: "#a1a1aa", fontSize: 10 }} domain={["dataMin", "dataMax"]} width={66} />
                <Tooltip content={<CustomTooltip />} />
                <Legend wrapperStyle={{ fontSize: "11px" }} />

                <Line type="monotone" dataKey="close" name="Close" stroke="#fafafa" strokeWidth={1.8} dot={false} />
                <Line type="monotone" dataKey="ema20" name="EMA20" stroke="#00E096" strokeWidth={1.2} dot={false} />
                <Line type="monotone" dataKey="sma50" name="SMA50" stroke="#3b82f6" strokeWidth={1.1} dot={false} />
                <Line type="monotone" dataKey="sma200" name="SMA200" stroke="#f59e0b" strokeWidth={1.1} dot={false} />

                {patternMarkers.map((marker) => (
                  <ReferenceDot
                    key={`${marker.date}-${marker.close}`}
                    x={marker.date}
                    y={marker.close}
                    r={4.5}
                    fill="#FF2D55"
                    stroke="#ffffff"
                    strokeWidth={1}
                    data-testid={`pattern-marker-${marker.date}`}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="mt-4 flex flex-wrap gap-2" data-testid="detected-pattern-badges">
            {(signal.patterns || []).map((pattern, index) => (
              <Badge key={`${pattern.name}-${index}`} className={`rounded-sm border text-[10px] ${breakoutBadgeClass(pattern)}`} data-testid={`detected-pattern-${index}-badge`}>
                {pattern.name} · {pattern.confirmed ? "Onaylı" : "İzleme"}
              </Badge>
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2" data-testid="pattern-analysis-secondary-grid">
        <Card className="border-border/70 bg-card/45" data-testid="score-breakdown-card">
          <CardHeader className="p-4 pb-2">
            <CardTitle className="text-base" data-testid="score-breakdown-title">Scoring Matrix</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 p-4 pt-2 text-sm">
            <div data-testid="score-breakdown-technical-row">
              <div className="mb-1 flex justify-between text-xs text-muted-foreground"><span>Teknik Kırılım</span><span>{breakdown.technical || 0}/30</span></div>
              <Progress value={((breakdown.technical || 0) / 30) * 100} className="h-2 rounded-sm" />
            </div>
            <div data-testid="score-breakdown-moving-average-row">
              <div className="mb-1 flex justify-between text-xs text-muted-foreground"><span>Hareketli Ortalama</span><span>{breakdown.moving_average || 0}/20</span></div>
              <Progress value={((breakdown.moving_average || 0) / 20) * 100} className="h-2 rounded-sm" />
            </div>
            <div data-testid="score-breakdown-volume-row">
              <div className="mb-1 flex justify-between text-xs text-muted-foreground"><span>Hacim Onayı</span><span>{breakdown.volume || 0}/20</span></div>
              <Progress value={((breakdown.volume || 0) / 20) * 100} className="h-2 rounded-sm" />
            </div>
            <div data-testid="score-breakdown-fundamental-row">
              <div className="mb-1 flex justify-between text-xs text-muted-foreground"><span>Temel Analiz</span><span>{breakdown.fundamental || 0}/30</span></div>
              <Progress value={((breakdown.fundamental || 0) / 30) * 100} className="h-2 rounded-sm" />
            </div>
          </CardContent>
        </Card>

        <Card className="border-border/70 bg-card/45" data-testid="indicator-snapshot-card">
          <CardHeader className="p-4 pb-2">
            <CardTitle className="text-base" data-testid="indicator-snapshot-title">Gösterge Snapshot</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-3 p-4 pt-2 text-xs" data-testid="indicator-snapshot-grid">
            <div className="rounded-sm border border-border/60 p-2" data-testid="indicator-rsi-box">
              <p className="text-muted-foreground">RSI(14)</p>
              <p className="font-mono text-sm font-semibold" data-testid="indicator-rsi-value">{signal.indicators?.rsi14 ?? "-"}</p>
            </div>
            <div className="rounded-sm border border-border/60 p-2" data-testid="indicator-macd-box">
              <p className="text-muted-foreground">MACD</p>
              <p className="font-mono text-sm font-semibold" data-testid="indicator-macd-value">{signal.indicators?.macd ?? "-"}</p>
            </div>
            <div className="rounded-sm border border-border/60 p-2" data-testid="indicator-golden-cross-box">
              <p className="text-muted-foreground">Golden Cross</p>
              <p className="font-mono text-sm font-semibold" data-testid="indicator-golden-cross-value">{signal.indicators?.golden_cross ? "Var" : "Yok"}</p>
            </div>
            <div className="rounded-sm border border-border/60 p-2" data-testid="indicator-bearish-divergence-box">
              <p className="text-muted-foreground">Negatif Uyumsuzluk</p>
              <p className="font-mono text-sm font-semibold" data-testid="indicator-bearish-divergence-value">{signal.indicators?.bearish_divergence ? "Evet" : "Hayır"}</p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};
