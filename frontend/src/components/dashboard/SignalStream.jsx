import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

const ACTION_CLASS_MAP = {
  "GÜÇLÜ AL": "border-primary/40 bg-primary/20 text-primary",
  AL: "border-emerald-400/40 bg-emerald-400/15 text-emerald-300",
  TUT: "border-blue-400/40 bg-blue-400/15 text-blue-300",
  SAT: "border-orange-400/40 bg-orange-400/15 text-orange-300",
  "GÜÇLÜ SAT": "border-destructive/40 bg-destructive/20 text-destructive",
};

const toTestId = (value) => value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

export const SignalStream = ({ signals, selectedSymbol, onSelect, loading }) => {
  return (
    <Card className="h-full border-border/70 bg-card/45 backdrop-blur-md" data-testid="signal-stream-card">
      <CardHeader className="border-b border-border/60 p-4">
        <CardTitle className="text-lg font-bold" data-testid="signal-stream-title">
          Sinyal Akışı
        </CardTitle>
      </CardHeader>
      <CardContent className="h-[calc(100vh-20rem)] overflow-y-auto p-2" data-testid="signal-stream-list-wrapper">
        {loading ? (
          <div className="space-y-2 p-2" data-testid="signal-stream-loading-state">
            {Array.from({ length: 8 }).map((_, index) => (
              <div
                key={`signal-skeleton-${index}`}
                className="h-16 animate-pulse rounded-sm border border-border/70 bg-muted/40"
                data-testid={`signal-skeleton-row-${index}`}
              />
            ))}
          </div>
        ) : signals.length === 0 ? (
          <div className="p-4 text-sm text-muted-foreground" data-testid="signal-stream-empty-state">
            Filtreye uyan hisse bulunamadı.
          </div>
        ) : (
          <div className="space-y-2" data-testid="signal-stream-items">
            {signals.map((signal) => {
              const isActive = selectedSymbol === signal.symbol;
              const actionClass = ACTION_CLASS_MAP[signal.action] || "border-border bg-muted text-foreground";
              return (
                <Button
                  key={signal.symbol}
                  variant="ghost"
                  className={`signal-card-enter h-auto w-full justify-start rounded-sm border p-3 text-left transition-colors duration-200 ${
                    isActive
                      ? "border-primary/60 bg-primary/10"
                      : "border-border/60 bg-card/50 hover:border-primary/30 hover:bg-primary/5"
                  }`}
                  onClick={() => onSelect(signal.symbol)}
                  data-testid={`signal-stream-item-${toTestId(signal.symbol)}-button`}
                >
                  <div className="w-full space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-sm font-semibold tracking-wide" data-testid={`signal-symbol-${toTestId(signal.symbol)}-value`}>
                        {signal.symbol}
                      </span>
                      <Badge className={`rounded-sm border text-[10px] font-bold uppercase tracking-wider ${actionClass}`} data-testid={`signal-action-${toTestId(signal.symbol)}-value`}>
                        {signal.action}
                      </Badge>
                    </div>

                    <div className="grid grid-cols-3 gap-1 text-xs" data-testid={`signal-metrics-${toTestId(signal.symbol)}-grid`}>
                      <div>
                        <p className="text-muted-foreground">Skor</p>
                        <p className="font-mono font-semibold" data-testid={`signal-score-${toTestId(signal.symbol)}-value`}>
                          {signal.bullish_score}
                        </p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Fiyat</p>
                        <p className="font-mono font-semibold" data-testid={`signal-price-${toTestId(signal.symbol)}-value`}>
                          {signal.last_price}
                        </p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Piyasa</p>
                        <p className="font-mono font-semibold" data-testid={`signal-market-${toTestId(signal.symbol)}-value`}>
                          {signal.market}
                        </p>
                      </div>
                    </div>
                  </div>
                </Button>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
};
