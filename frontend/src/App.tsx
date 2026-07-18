import React, { useState, useEffect, useCallback } from 'react';
import { TrendingUp, Calendar, BarChart3, Table2, Building2, Bot, Menu, X } from 'lucide-react';
import HomeTab from './components/HomeTab';
import CalendarTab from './components/CalendarTab';
import FundamentalTab from './components/FundamentalTab';
import BiasTab from './components/BiasTab';
import CftcTab from './components/CftcTab';
import FredTab from './components/FredTab';

export interface DataStore {
  calendar: any | null;
  macro_data: any | null;
  cftc_report: any | null;
  master_bias: any | null;
  ai_insights: any | null;
}

type TabId = 'home' | 'calendar' | 'fundamental' | 'bias' | 'cftc' | 'fred';

interface TabConfig {
  id: TabId;
  label: string;
  icon: React.ReactNode;
}

const TABS: TabConfig[] = [
  { id: 'home', label: 'Home', icon: <TrendingUp size={16} /> },
  { id: 'calendar', label: 'Calendar', icon: <Calendar size={16} /> },
  { id: 'fundamental', label: 'Fundamental', icon: <BarChart3 size={16} /> },
  { id: 'bias', label: 'Bias', icon: <Table2 size={16} /> },
  { id: 'cftc', label: 'CFTC', icon: <Building2 size={16} /> },
  { id: 'fred', label: 'FRED', icon: <Building2 size={16} /> },
];

const DATA_FILES: { key: keyof DataStore; path: string }[] = [
  { key: 'calendar', path: './data/calendar.json' },
  { key: 'macro_data', path: './data/macro_data.json' },
  { key: 'cftc_report', path: './data/cftc_report.json' },
  { key: 'master_bias', path: './data/master_bias.json' },
  { key: 'ai_insights', path: './data/ai_insights.json' },
];

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>('home');
  const [data, setData] = useState<DataStore>({
    calendar: null, macro_data: null, cftc_report: null,
    master_bias: null, ai_insights: null,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    const results: DataStore = {
      calendar: null, macro_data: null, cftc_report: null,
      master_bias: null, ai_insights: null,
    };
    let hasError = false;

    for (const { key, path } of DATA_FILES) {
      try {
        const resp = await fetch(path);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${path}`);
        results[key] = await resp.json();
      } catch (err: any) {
        console.warn(`Failed to load ${path}:`, err.message);
        hasError = true;
      }
    }

    setData(results);
    if (hasError) setError('Some data files could not be loaded. The pipeline may still be running.');
    setLoading(false);
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const renderTab = () => {
    if (loading) {
      return (
        <div className="flex items-center justify-center py-20">
          <div className="text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-accent-blue mx-auto mb-4" />
            <p className="text-gray-500 text-sm">Loading fundamental data...</p>
          </div>
        </div>
      );
    }

    switch (activeTab) {
      case 'home': return <HomeTab data={data} />;
      case 'calendar': return <CalendarTab data={data.calendar} />;
      case 'fundamental': return <FundamentalTab data={data} />;
      case 'bias': return <BiasTab data={data.master_bias} />;
      case 'cftc': return <CftcTab data={data.cftc_report} />;
      case 'fred': return <FredTab data={data.macro_data} />;
      default: return null;
    }
  };

  return (
    <div className="min-h-screen bg-dark-bg">
      {/* ═══ Header ═══ */}
      <header className="bg-dark-card border-b border-dark-border sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex items-center justify-between h-14">
            {/* Logo */}
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2">
                <TrendingUp className="text-emerald-400" size={22} />
                <h1 className="text-base font-bold text-white tracking-tight">
                  Bulls & Bears <span className="text-emerald-400">Fundamentals</span>
                </h1>
              </div>
              <span className="hidden sm:inline text-[10px] text-gray-600 uppercase tracking-widest border-l border-dark-border pl-3">
                Macro Screener
              </span>
            </div>

            {/* Desktop Nav */}
            <nav className="hidden md:flex items-center gap-1">
              {TABS.map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`tab-btn flex items-center gap-1.5 ${
                    activeTab === tab.id ? 'active' : ''
                  }`}
                >
                  {tab.icon}
                  {tab.label}
                </button>
              ))}
            </nav>

            {/* Mobile menu button */}
            <button
              className="md:hidden text-gray-400 hover:text-white p-1"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            >
              {mobileMenuOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>

          {/* Mobile Nav */}
          {mobileMenuOpen && (
            <div className="md:hidden pb-3 flex flex-wrap gap-1">
              {TABS.map(tab => (
                <button
                  key={tab.id}
                  onClick={() => { setActiveTab(tab.id); setMobileMenuOpen(false); }}
                  className={`tab-btn flex items-center gap-1.5 text-xs ${
                    activeTab === tab.id ? 'active' : ''
                  }`}
                >
                  {tab.icon}
                  {tab.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </header>

      {/* ═══ Error Banner ═══ */}
      {error && (
        <div className="max-w-7xl mx-auto px-4 pt-4">
          <div className="bg-yellow-900/30 border border-yellow-700/30 rounded-lg px-4 py-3 text-sm text-yellow-400">
            ⚠️ {error}
          </div>
        </div>
      )}

      {/* ═══ Main Content ═══ */}
      <main className="max-w-7xl mx-auto px-4 py-6">
        {renderTab()}
      </main>

      {/* ═══ TradersYard Partner Banner ═══ */}
      <footer className="border-t border-dark-border mt-8">
        <div className="max-w-7xl mx-auto px-4 py-6">
          <div className="cta-banner">
            <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
              <div className="text-left">
                <h3 className="text-sm font-semibold text-white">
                  🏆 Partnered Firm — <span className="text-emerald-400">TradersYard</span>
                </h3>
                <p className="text-xs text-gray-400 mt-1">
                  Get funded and trade with confidence. Use code <span className="discount-code text-sm">ROSHAN</span> for exclusive discount.
                </p>
              </div>
              <a
                href="https://shop.tradersyard.com/ref/1486/"
                target="_blank"
                rel="noopener noreferrer"
                className="cta-btn whitespace-nowrap"
              >
                Get Funded at TradersYard →
              </a>
            </div>
          </div>
          <div className="mt-4 text-center text-[10px] text-gray-600">
            Bulls & Bears Fundamentals — Data sourced from FRED, CFTC, AlphaVantage, FMP, Finnhub, Yahoo Finance
          </div>
        </div>
      </footer>
    </div>
  );
}