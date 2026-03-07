import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const resolveTradingViewSymbol = (symbol = "AAPL") => {
  if (symbol.endsWith(".IS")) {
    return `BIST:${symbol.replace(".IS", "")}`;
  }
  return `NASDAQ:${symbol.replace("-", ".")}`;
};

export const TradingViewPanel = ({ signal, scannerState }) => {
  const fallbackSymbol = "AAPL";
  const symbol = signal?.symbol || fallbackSymbol;
  const tvSymbol = resolveTradingViewSymbol(symbol);

  const widgetUrl = `https://s.tradingview.com/widgetembed/?symbol=${encodeURIComponent(tvSymbol)}&interval=D&hidesidetoolbar=0&symboledit=1&saveimage=1&toolbarbg=1f2937&theme=dark&style=1&timezone=Etc%2FUTC&studies=%5B%5D&withdateranges=1&hide_top_toolbar=0&hide_legend=0&locale=tr`;

  return (
    <div className="space-y-4" data-testid="tradingview-panel-container">
      <Card className="border-border/70 bg-card/45 backdrop-blur-md" data-testid="tradingview-widget-card">
        <CardHeader className="border-b border-border/60 p-4">
          <CardTitle className="text-base" data-testid="tradingview-widget-title">TradingView Widget</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 p-4">
          <Badge className="rounded-sm border border-border bg-muted/20 text-xs text-foreground" data-testid="tradingview-widget-symbol-badge">
            {tvSymbol}
          </Badge>
          <div className="aspect-[4/3] overflow-hidden rounded-sm border border-border/70" data-testid="tradingview-widget-frame-wrapper">
            <iframe
              title="TradingView"
              src={widgetUrl}
              className="h-full w-full"
              frameBorder="0"
              allowFullScreen
              data-testid="tradingview-widget-iframe"
            />
          </div>
        </CardContent>
      </Card>

      <Card className="border-border/70 bg-card/45" data-testid="risk-management-card">
        <CardHeader className="p-4 pb-2">
          <CardTitle className="text-base" data-testid="risk-management-title">Risk Yönetimi</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-2 p-4 pt-2 text-xs" data-testid="risk-management-grid">
          <div className="rounded-sm border border-border/60 p-2" data-testid="risk-entry-box">
            <p className="text-muted-foreground">Giriş</p>
            <p className="font-mono text-sm font-semibold" data-testid="risk-entry-value">{signal?.risk?.entry_price ?? "-"}</p>
          </div>
          <div className="rounded-sm border border-border/60 p-2" data-testid="risk-atr-box">
            <p className="text-muted-foreground">ATR(14)</p>
            <p className="font-mono text-sm font-semibold" data-testid="risk-atr-value">{signal?.risk?.atr ?? "-"}</p>
          </div>
          <div className="rounded-sm border border-border/60 p-2" data-testid="risk-stop-loss-box">
            <p className="text-muted-foreground">Stop-Loss</p>
            <p className="font-mono text-sm font-semibold text-destructive" data-testid="risk-stop-loss-value">{signal?.risk?.stop_loss ?? "-"}</p>
          </div>
          <div className="rounded-sm border border-border/60 p-2" data-testid="risk-take-profit-box">
            <p className="text-muted-foreground">Take-Profit</p>
            <p className="font-mono text-sm font-semibold text-primary" data-testid="risk-take-profit-value">{signal?.risk?.take_profit ?? "-"}</p>
          </div>
        </CardContent>
      </Card>

      <Card className="border-border/70 bg-card/45" data-testid="scanner-health-card">
        <CardHeader className="p-4 pb-2">
          <CardTitle className="text-base" data-testid="scanner-health-title">Tarama Sağlığı</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 p-4 pt-2 text-xs text-muted-foreground" data-testid="scanner-health-content">
          <p data-testid="scanner-health-running-value">Durum: {scannerState?.running ? "Çalışıyor" : "Beklemede"}</p>
          <p data-testid="scanner-health-duration-value">Süre: {scannerState?.last_duration_seconds ?? "-"} sn</p>
          <p data-testid="scanner-health-error-value">Hata: {scannerState?.last_error || "Yok"}</p>
        </CardContent>
      </Card>
    </div>
  );
};
