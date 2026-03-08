import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/sonner";
import { DashboardControls } from "@/components/dashboard/DashboardControls";
import { PatternChartPanel } from "@/components/dashboard/PatternChartPanel";
import { SignalDetailSheet } from "@/components/dashboard/SignalDetailSheet";
import { SignalStream } from "@/components/dashboard/SignalStream";
import { TradingViewPanel } from "@/components/dashboard/TradingViewPanel";
import {
  autoEnrichSignal,
  analyzeSymbolOnDemand,
  explainSignal,
  fetchConfig,
  fetchScannerState,
  fetchSignalDetail,
  fetchSignals,
  exportSignalsExcel,
  generateSignalVisualization,
  reanalyzeSignal,
  runScanner,
} from "@/services/signalApi";

const replaceSignal = (list, updatedSignal) => {
  const index = list.findIndex((item) => item.symbol === updatedSignal.symbol);
  if (index === -1) {
    return [updatedSignal, ...list];
  }
  const clone = [...list];
  clone[index] = updatedSignal;
  return clone;
};

export default function DashboardPage() {
  const [config, setConfig] = useState(null);
  const [scannerState, setScannerState] = useState(null);
  const [signals, setSignals] = useState([]);
  const [loadingSignals, setLoadingSignals] = useState(false);
  const [market, setMarket] = useState("ALL");
  const [action, setAction] = useState("ALL");
  const [symbolInput, setSymbolInput] = useState("");
  const [selectedSymbol, setSelectedSymbol] = useState("");
  const [isDetailOpen, setIsDetailOpen] = useState(false);
  const [explaining, setExplaining] = useState(false);
  const [analyzingSymbol, setAnalyzingSymbol] = useState(false);
  const [refreshCooldown, setRefreshCooldown] = useState(0);
  const [isExportOpen, setIsExportOpen] = useState(false);
  const [exportMarkets, setExportMarkets] = useState(["NASDAQ", "BIST"]);
  const [exportActions, setExportActions] = useState(["GÜÇLÜ AL", "AL", "TUT", "SAT", "GÜÇLÜ SAT"]);
  const [exporting, setExporting] = useState(false);

  const loadScannerState = useCallback(async () => {
    try {
      const state = await fetchScannerState();
      setScannerState(state);
    } catch (error) {
      console.error(error);
    }
  }, []);

  const loadSignals = useCallback(async () => {
    setLoadingSignals(true);
    try {
      const data = await fetchSignals({ market, action, limit: 1100 });
      setSignals(data);
      setSelectedSymbol((previousSymbol) => {
        if (data.length === 0) {
          return "";
        }
        if (data.some((item) => item.symbol === previousSymbol)) {
          return previousSymbol;
        }
        return data[0].symbol;
      });
    } catch (error) {
      console.error(error);
      toast.error("Sinyaller alınamadı.");
    } finally {
      setLoadingSignals(false);
    }
  }, [market, action]);

  const selectedSignal = useMemo(
    () => signals.find((item) => item.symbol === selectedSymbol) || null,
    [signals, selectedSymbol],
  );

  const loadSignalDetail = useCallback(async (symbol) => {
    try {
      const detail = await fetchSignalDetail(symbol);
      setSignals((previous) => replaceSignal(previous, detail));
      return detail;
    } catch (error) {
      console.error(error);
      return null;
    }
  }, []);

  const handleSignalSelect = async (symbol) => {
    setSelectedSymbol(symbol);
    setIsDetailOpen(true);
    const detail = await loadSignalDetail(symbol);

    if (detail) {
      try {
        setExplaining(true);
        await autoEnrichSignal(symbol);
        await loadSignalDetail(symbol);
      } catch (error) {
        console.error(error);
        toast.error("Formasyon görseli otomatik üretilemedi.");
      } finally {
        setExplaining(false);
      }
    }
  };

  const handleAnalyzeSymbol = async () => {
    if (!symbolInput.trim()) {
      return;
    }

    setAnalyzingSymbol(true);
    try {
      const analyzed = await analyzeSymbolOnDemand(symbolInput.trim().toUpperCase());
      setMarket("ALL");
      setAction("ALL");
      setSignals((previous) => replaceSignal(previous, analyzed));
      setSelectedSymbol(analyzed.symbol);
      setIsDetailOpen(true);
      setSymbolInput(analyzed.symbol);
      toast.success(`${analyzed.symbol} için anlık analiz üretildi.`);
    } catch (error) {
      console.error(error);
      toast.error("Sembol analiz edilemedi.");
    } finally {
      setAnalyzingSymbol(false);
    }
  };

  const handleRefreshAll = async () => {
    if (refreshCooldown > 0) {
      return;
    }
    try {
      const result = await runScanner();
      toast.success(result.message || "Tarama tetiklendi.");
      setRefreshCooldown(30);
      await loadSignals();
      await loadScannerState();
    } catch (error) {
      console.error(error);
      toast.error("Veri güncelleme başlatılamadı.");
    }
  };

  const handleReanalyze = async (symbol) => {
    setExplaining(true);
    try {
      const updated = await reanalyzeSignal(symbol);
      setSignals((previous) => replaceSignal(previous, updated));
      setSelectedSymbol(updated.symbol);
      toast.success(`${updated.symbol} yeniden analiz edildi.`);
    } catch (error) {
      console.error(error);
      toast.error("Yeniden analiz başarısız oldu.");
    } finally {
      setExplaining(false);
    }
  };

  const handleExplain = async (symbol) => {
    setExplaining(true);
    try {
      const response = await explainSignal(symbol);
      const detail = await loadSignalDetail(symbol);
      if (!detail) {
        setSignals((previous) =>
          previous.map((item) =>
            item.symbol === symbol ? { ...item, ai_summary: response.summary } : item,
          ),
        );
      }
      toast.success(`${response.symbol} için AI raporu üretildi.`);
    } catch (error) {
      console.error(error);
      toast.error("AI raporu üretilemedi.");
    } finally {
      setExplaining(false);
    }
  };

  const handleRegenerateImage = async (symbol) => {
    setExplaining(true);
    try {
      await generateSignalVisualization(symbol);
      await loadSignalDetail(symbol);
      toast.success(`${symbol} görseli yeniden oluşturuldu.`);
    } catch (error) {
      console.error(error);
      toast.error("Formasyon görseli yeniden oluşturulamadı.");
    } finally {
      setExplaining(false);
    }
  };

  const toggleArrayValue = (value, currentValues, setValues) => {
    if (currentValues.includes(value)) {
      setValues(currentValues.filter((item) => item !== value));
    } else {
      setValues([...currentValues, value]);
    }
  };

  const handleExportExcel = async () => {
    setExporting(true);
    try {
      const blob = await exportSignalsExcel({ markets: exportMarkets, actions: exportActions });
      const blobUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = blobUrl;
      link.download = "sinyal_raporu.xlsx";
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(blobUrl);
      setIsExportOpen(false);
      toast.success("Excel dosyası oluşturuldu ve indirildi.");
    } catch (error) {
      console.error(error);
      toast.error("Excel dışa aktarma başarısız oldu.");
    } finally {
      setExporting(false);
    }
  };

  useEffect(() => {
    const initialize = async () => {
      try {
        const data = await fetchConfig();
        setConfig(data);
      } catch (error) {
        console.error(error);
      }
      await loadScannerState();
    };

    initialize();
  }, [loadScannerState]);

  useEffect(() => {
    loadSignals();
  }, [loadSignals]);

  useEffect(() => {
    if (refreshCooldown <= 0) {
      return;
    }
    const timer = setInterval(() => {
      setRefreshCooldown((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, [refreshCooldown]);

  useEffect(() => {
    const refreshMillis = (config?.refresh_seconds || 300) * 1000;
    const refreshInterval = setInterval(() => {
      loadSignals();
      loadScannerState();
    }, refreshMillis);

    return () => clearInterval(refreshInterval);
  }, [config?.refresh_seconds, loadSignals, loadScannerState]);

  useEffect(() => {
    const scannerInterval = setInterval(() => {
      loadScannerState();
    }, 15000);

    return () => clearInterval(scannerInterval);
  }, [loadScannerState]);

  return (
    <main className="dashboard-shell space-y-4 p-4 pb-20 md:p-6 md:pb-24" data-testid="dashboard-page-main">
      <DashboardControls
        market={market}
        action={action}
        symbolInput={symbolInput}
        scannerState={scannerState}
        onMarketChange={setMarket}
        onActionChange={setAction}
        onSymbolInputChange={setSymbolInput}
        onAnalyzeSymbol={handleAnalyzeSymbol}
        onRefreshAll={handleRefreshAll}
        loading={loadingSignals}
        analyzing={analyzingSymbol}
        refreshCooldown={refreshCooldown}
      />

      <section className="grid grid-cols-12 gap-4" data-testid="dashboard-main-grid">
        <div className="col-span-12 lg:col-span-3" data-testid="dashboard-left-signal-stream-column">
          <SignalStream
            signals={signals}
            selectedSymbol={selectedSymbol}
            onSelect={handleSignalSelect}
            loading={loadingSignals}
            onOpenExportModal={() => setIsExportOpen(true)}
          />
        </div>

        <div className="col-span-12 lg:col-span-6" data-testid="dashboard-center-chart-column">
          <PatternChartPanel signal={selectedSignal} />
        </div>

        <div className="col-span-12 lg:col-span-3" data-testid="dashboard-right-tradingview-column">
          <TradingViewPanel signal={selectedSignal} scannerState={scannerState} />
        </div>
      </section>

      <SignalDetailSheet
        open={isDetailOpen}
        signal={selectedSignal}
        explaining={explaining}
        onOpenChange={setIsDetailOpen}
        onExplain={handleExplain}
        onReanalyze={handleReanalyze}
        onRegenerateImage={handleRegenerateImage}
      />

      <footer
        className="fixed bottom-0 left-0 right-0 z-40 border-t border-border/70 bg-background/90 px-4 py-2 text-center text-xs text-zinc-400 backdrop-blur-md"
        data-testid="legal-disclaimer-footer"
      >
        YASAL UYARI: Bu platformda sunulan veriler ve yapay zeka sinyalleri yatırım tavsiyesi değildir. Yatırım kararlarınızı lisanslı danışmanlar eşliğinde veriniz.
      </footer>

      <Dialog open={isExportOpen} onOpenChange={setIsExportOpen}>
        <DialogContent className="max-w-xl rounded-sm border-border bg-background p-5" data-testid="export-filter-modal">
          <DialogTitle data-testid="export-filter-modal-title">Verileri Dışa Aktar (Excel)</DialogTitle>

          <div className="space-y-5" data-testid="export-filter-modal-content">
            <section className="space-y-2" data-testid="export-market-filter-section">
              <p className="text-sm font-semibold text-foreground" data-testid="export-market-filter-title">Borsa Seçimi</p>
              <div className="space-y-2 rounded-sm border border-border/70 p-3">
                {["NASDAQ", "BIST"].map((marketOption) => (
                  <Label key={marketOption} className="flex cursor-pointer items-center gap-2 text-sm" data-testid={`export-market-option-${marketOption.toLowerCase()}`}>
                    <input
                      type="checkbox"
                      checked={exportMarkets.includes(marketOption)}
                      onChange={() => toggleArrayValue(marketOption, exportMarkets, setExportMarkets)}
                      data-testid={`export-market-${marketOption.toLowerCase()}-checkbox`}
                    />
                    {marketOption}
                  </Label>
                ))}
              </div>
            </section>

            <section className="space-y-2" data-testid="export-action-filter-section">
              <p className="text-sm font-semibold text-foreground" data-testid="export-action-filter-title">Sinyal Durumu Seçimi</p>
              <div className="grid grid-cols-2 gap-2 rounded-sm border border-border/70 p-3">
                {[
                  { value: "GÜÇLÜ AL", label: "Güçlü Al" },
                  { value: "AL", label: "Al" },
                  { value: "TUT", label: "Tut" },
                  { value: "SAT", label: "Sat" },
                  { value: "GÜÇLÜ SAT", label: "Güçlü Sat" },
                ].map((actionOption) => (
                  <Label key={actionOption.value} className="flex cursor-pointer items-center gap-2 text-sm" data-testid={`export-action-option-${actionOption.value.toLowerCase().replace(/\s+/g, "-")}`}>
                    <input
                      type="checkbox"
                      checked={exportActions.includes(actionOption.value)}
                      onChange={() => toggleArrayValue(actionOption.value, exportActions, setExportActions)}
                      data-testid={`export-action-${actionOption.value.toLowerCase().replace(/\s+/g, "-")}-checkbox`}
                    />
                    {actionOption.label}
                  </Label>
                ))}
              </div>
            </section>

            <div className="flex justify-end gap-2" data-testid="export-filter-actions-row">
              <Button variant="outline" onClick={() => setIsExportOpen(false)} data-testid="export-filter-cancel-button">Vazgeç</Button>
              <Button
                onClick={handleExportExcel}
                disabled={exporting || (exportMarkets.length === 0 && exportActions.length === 0)}
                data-testid="export-filter-generate-file-button"
              >
                {exporting ? "Oluşturuluyor..." : "Dosyayı Oluştur"}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </main>
  );
}
