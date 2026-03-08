import { useCallback, useEffect, useMemo, useState } from "react";
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
    </main>
  );
}
