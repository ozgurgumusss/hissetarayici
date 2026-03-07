import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Separator } from "@/components/ui/separator";

const patternClass = (direction) =>
  direction === "bullish"
    ? "border-primary/40 bg-primary/15 text-primary"
    : "border-destructive/40 bg-destructive/15 text-destructive";

export const SignalDetailSheet = ({ open, signal, explaining, onOpenChange, onExplain }) => {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-full overflow-y-auto border-border/80 bg-background/95 p-0 sm:max-w-2xl"
        data-testid="signal-detail-sheet"
      >
        {!signal ? (
          <div className="p-6 text-sm text-muted-foreground" data-testid="signal-detail-empty-state">
            Detay için soldan bir hisse seçin.
          </div>
        ) : (
          <div className="animate-slide-in-right space-y-5 p-6" data-testid="signal-detail-content">
            <SheetHeader className="space-y-2 text-left" data-testid="signal-detail-header">
              <SheetTitle className="font-heading text-2xl font-black" data-testid="signal-detail-title">
                {signal.symbol} · AI Raporu
              </SheetTitle>
              <SheetDescription className="text-sm text-muted-foreground" data-testid="signal-detail-subtitle">
                Karar: {signal.action} · Bullish Score: {signal.bullish_score}
              </SheetDescription>
            </SheetHeader>

            <div className="flex flex-wrap gap-2" data-testid="signal-detail-pattern-badges">
              {(signal.patterns || []).map((pattern, index) => (
                <Badge key={`${pattern.name}-${index}`} className={`rounded-sm border ${patternClass(pattern.direction)}`} data-testid={`signal-detail-pattern-${index}-badge`}>
                  {pattern.name} · {pattern.confirmed ? "Onay" : "Takip"}
                </Badge>
              ))}
            </div>

            <Separator />

            <section className="space-y-2" data-testid="signal-detail-technical-section">
              <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground" data-testid="signal-detail-technical-title">Teknik Durum</h3>
              <div className="grid grid-cols-2 gap-2 text-sm" data-testid="signal-detail-technical-grid">
                <div className="rounded-sm border border-border/70 p-2" data-testid="signal-detail-rsi-box">
                  <p className="text-muted-foreground">RSI(14)</p>
                  <p className="font-mono" data-testid="signal-detail-rsi-value">{signal.indicators?.rsi14 ?? "-"}</p>
                </div>
                <div className="rounded-sm border border-border/70 p-2" data-testid="signal-detail-macd-box">
                  <p className="text-muted-foreground">MACD</p>
                  <p className="font-mono" data-testid="signal-detail-macd-value">{signal.indicators?.macd ?? "-"}</p>
                </div>
                <div className="rounded-sm border border-border/70 p-2" data-testid="signal-detail-golden-cross-box">
                  <p className="text-muted-foreground">Golden Cross</p>
                  <p className="font-mono" data-testid="signal-detail-golden-cross-value">{signal.indicators?.golden_cross ? "Var" : "Yok"}</p>
                </div>
                <div className="rounded-sm border border-border/70 p-2" data-testid="signal-detail-bearish-div-box">
                  <p className="text-muted-foreground">Negatif Uyumsuzluk</p>
                  <p className="font-mono" data-testid="signal-detail-bearish-div-value">{signal.indicators?.bearish_divergence ? "Evet" : "Hayır"}</p>
                </div>
              </div>
            </section>

            <section className="space-y-2" data-testid="signal-detail-fundamental-section">
              <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground" data-testid="signal-detail-fundamental-title">Temel Durum</h3>
              <div className="grid grid-cols-2 gap-2 text-sm" data-testid="signal-detail-fundamental-grid">
                <div className="rounded-sm border border-border/70 p-2" data-testid="signal-detail-pe-box">
                  <p className="text-muted-foreground">F/K (P/E)</p>
                  <p className="font-mono" data-testid="signal-detail-pe-value">{signal.fundamental?.pe ?? "-"}</p>
                </div>
                <div className="rounded-sm border border-border/70 p-2" data-testid="signal-detail-pb-box">
                  <p className="text-muted-foreground">PD/DD (P/B)</p>
                  <p className="font-mono" data-testid="signal-detail-pb-value">{signal.fundamental?.pb ?? "-"}</p>
                </div>
                <div className="rounded-sm border border-border/70 p-2" data-testid="signal-detail-current-ratio-box">
                  <p className="text-muted-foreground">Cari Oran</p>
                  <p className="font-mono" data-testid="signal-detail-current-ratio-value">{signal.fundamental?.current_ratio ?? "-"}</p>
                </div>
                <div className="rounded-sm border border-border/70 p-2" data-testid="signal-detail-eps-growth-box">
                  <p className="text-muted-foreground">EPS Büyümesi</p>
                  <p className="font-mono" data-testid="signal-detail-eps-growth-value">{signal.fundamental?.eps_growth_qoq ?? "-"}</p>
                </div>
              </div>
            </section>

            <section className="space-y-2" data-testid="signal-detail-risk-section">
              <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground" data-testid="signal-detail-risk-title">Aksiyon ve Risk</h3>
              <div className="grid grid-cols-3 gap-2 text-sm" data-testid="signal-detail-risk-grid">
                <div className="rounded-sm border border-border/70 p-2" data-testid="signal-detail-entry-box">
                  <p className="text-muted-foreground">Giriş</p>
                  <p className="font-mono" data-testid="signal-detail-entry-value">{signal.risk?.entry_price ?? "-"}</p>
                </div>
                <div className="rounded-sm border border-border/70 p-2" data-testid="signal-detail-stop-loss-box">
                  <p className="text-muted-foreground">Stop-Loss</p>
                  <p className="font-mono text-destructive" data-testid="signal-detail-stop-loss-value">{signal.risk?.stop_loss ?? "-"}</p>
                </div>
                <div className="rounded-sm border border-border/70 p-2" data-testid="signal-detail-take-profit-box">
                  <p className="text-muted-foreground">Take-Profit</p>
                  <p className="font-mono text-primary" data-testid="signal-detail-take-profit-value">{signal.risk?.take_profit ?? "-"}</p>
                </div>
              </div>
            </section>

            <div className="space-y-2" data-testid="signal-detail-ai-summary-section">
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground" data-testid="signal-detail-ai-summary-title">Yapay Zeka Raporu</h3>
                <Button
                  className="rounded-sm bg-primary text-primary-foreground hover:bg-primary/90"
                  onClick={() => onExplain(signal.symbol)}
                  disabled={explaining}
                  data-testid="signal-detail-generate-ai-button"
                >
                  {explaining ? "Üretiliyor..." : "Raporu Üret / Güncelle"}
                </Button>
              </div>

              <div className="rounded-sm border border-border/70 bg-card/60 p-3" data-testid="signal-detail-ai-summary-content">
                <p className="whitespace-pre-line text-sm leading-relaxed text-foreground" data-testid="signal-detail-ai-summary-text">
                  {signal.ai_summary || "Henüz AI raporu üretilmedi. Butona basarak oluşturabilirsiniz."}
                </p>
              </div>
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
};
