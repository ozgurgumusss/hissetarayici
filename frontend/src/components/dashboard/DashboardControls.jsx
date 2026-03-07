import { Activity, RefreshCw, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const ACTION_OPTIONS = ["ALL", "GÜÇLÜ AL", "AL", "TUT", "SAT", "GÜÇLÜ SAT"];

const toTestId = (value) => value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

export const DashboardControls = ({
  market,
  action,
  search,
  scannerState,
  onMarketChange,
  onActionChange,
  onSearchChange,
  onManualScan,
  onReload,
  loading,
}) => {
  const lastRun = scannerState?.last_run
    ? new Date(scannerState.last_run).toLocaleString("tr-TR")
    : "Henüz çalışmadı";

  return (
    <Card className="border-border/70 bg-card/50 backdrop-blur-md" data-testid="dashboard-controls-card">
      <CardContent className="flex flex-col gap-4 p-4 md:p-5">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
          <div data-testid="dashboard-header-info">
            <h1 className="font-heading text-3xl font-black tracking-tight text-foreground" data-testid="dashboard-main-title">
              Algorithmic Signal Matrix
            </h1>
            <p className="mt-1 text-sm text-muted-foreground" data-testid="dashboard-main-subtitle">
              US + BIST günlük tarama, formasyon kırılımları ve açıklanabilir AI raporu
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2" data-testid="dashboard-actions-row">
            <Button
              variant="outline"
              className="rounded-sm border-border bg-transparent"
              onClick={onReload}
              disabled={loading}
              data-testid="dashboard-refresh-signals-button"
            >
              <RefreshCw className="h-4 w-4" />
              Listeyi Yenile
            </Button>
            <Button
              className="rounded-sm bg-primary text-primary-foreground hover:bg-primary/90"
              onClick={onManualScan}
              data-testid="dashboard-run-manual-scan-button"
            >
              <Play className="h-4 w-4" />
              Manuel Tarama
            </Button>
          </div>
        </div>

        <div className="grid gap-3 lg:grid-cols-12" data-testid="dashboard-filter-grid">
          <div className="lg:col-span-3" data-testid="market-filter-section">
            <p className="mb-1 text-xs font-bold uppercase tracking-wider text-muted-foreground" data-testid="market-filter-label">
              Piyasa
            </p>
            <div className="flex flex-wrap gap-2" data-testid="market-filter-buttons">
              {["ALL", "US", "BIST"].map((item) => (
                <Button
                  key={item}
                  variant={market === item ? "default" : "outline"}
                  className="h-8 rounded-sm px-3 text-xs"
                  onClick={() => onMarketChange(item)}
                  data-testid={`market-filter-${toTestId(item)}-button`}
                >
                  {item}
                </Button>
              ))}
            </div>
          </div>

          <div className="lg:col-span-6" data-testid="action-filter-section">
            <p className="mb-1 text-xs font-bold uppercase tracking-wider text-muted-foreground" data-testid="action-filter-label">
              Sinyal Türü
            </p>
            <div className="flex flex-wrap gap-2" data-testid="action-filter-buttons">
              {ACTION_OPTIONS.map((item) => (
                <Button
                  key={item}
                  variant={action === item ? "default" : "outline"}
                  className="h-8 rounded-sm px-3 text-xs"
                  onClick={() => onActionChange(item)}
                  data-testid={`action-filter-${toTestId(item)}-button`}
                >
                  {item}
                </Button>
              ))}
            </div>
          </div>

          <div className="lg:col-span-3" data-testid="symbol-search-section">
            <p className="mb-1 text-xs font-bold uppercase tracking-wider text-muted-foreground" data-testid="symbol-search-label">
              Hisse Ara
            </p>
            <Input
              value={search}
              placeholder="AAPL, THYAO..."
              onChange={(event) => onSearchChange(event.target.value)}
              className="h-8 rounded-sm border-border bg-input/60 font-mono"
              data-testid="symbol-search-input"
            />
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-4 border-t border-border/70 pt-3" data-testid="scanner-status-row">
          <div className="flex items-center gap-2 text-sm" data-testid="scanner-running-state">
            <Activity className={`h-4 w-4 ${scannerState?.running ? "text-primary animate-scan-pulse" : "text-muted-foreground"}`} />
            <span className="text-muted-foreground">Tarayıcı Durumu:</span>
            <span className="font-semibold text-foreground" data-testid="scanner-status-value">
              {scannerState?.running ? "ÇALIŞIYOR" : "BEKLEMEDE"}
            </span>
          </div>
          <p className="text-sm text-muted-foreground" data-testid="scanner-last-run-value">
            Son çalışma: {lastRun}
          </p>
          <p className="text-sm text-muted-foreground" data-testid="scanner-processed-count-value">
            Son taranan sembol: {scannerState?.last_scanned_count ?? 0}
          </p>
        </div>
      </CardContent>
    </Card>
  );
};
