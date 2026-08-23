import React, { useMemo, useState } from 'react';
import { Search, ExternalLink, Newspaper } from 'lucide-react';

interface NewsArticle {
  headline: string;
  timestamp: string;
  currency_tags: string[];
  impact: string;
  source_link: string;
  snippet: string;
}

interface Props {
  data: any;
}

// Filter pills aligned with the task spec: ALL, USD, EUR, GBP, JPY, AUD, CAD,
// GOLD, CRYPTO. GOLD maps to XAU tag; CRYPTO maps to BTC/ETH/etc.
const ALL_TAGS = ['USD', 'EUR', 'GBP', 'JPY', 'AUD', 'CAD', 'GOLD', 'CRYPTO'];

// Map display pill -> underlying currency_tags to match
const TAG_MATCH: Record<string, string[]> = {
  USD: ['USD'],
  EUR: ['EUR'],
  GBP: ['GBP'],
  JPY: ['JPY'],
  AUD: ['AUD'],
  CAD: ['CAD'],
  GOLD: ['XAU'],
  CRYPTO: ['BTC', 'ETH', 'LTC', 'SOL', 'XRP', 'AVAX', 'SUI', 'XLM'],
};

export default function NewsTab({ data }: Props) {
  const articles: NewsArticle[] = data?.articles || [];
  const [search, setSearch] = useState('');
  const [activeTag, setActiveTag] = useState<string | null>(null);

  const filteredArticles = useMemo(() => {
    let filtered = articles;
    if (activeTag) {
      const matchTags = TAG_MATCH[activeTag] || [activeTag];
      filtered = filtered.filter(a =>
        a.currency_tags?.some(tag => matchTags.includes(tag))
      );
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      filtered = filtered.filter(a =>
        a.headline?.toLowerCase().includes(q) ||
        a.snippet?.toLowerCase().includes(q)
      );
    }
    return filtered;
  }, [articles, search, activeTag]);

  const getImpactBadge = (impact: string) => {
    const i = (impact || 'medium').toLowerCase();
    if (i === 'high') return 'bg-red-900/40 text-red-400 border-red-700/40';
    if (i === 'medium' || i === 'med') return 'bg-yellow-900/40 text-yellow-400 border-yellow-700/40';
    return 'bg-gray-700/40 text-gray-400 border-gray-600/40';
  };

  const formatTimestamp = (ts: string) => {
    if (!ts) return '';
    try {
      const d = new Date(ts);
      if (isNaN(d.getTime())) return ts;
      return d.toLocaleString('en-US', {
        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
      });
    } catch {
      return ts;
    }
  };

  if (!articles.length) {
    return (
      <div className="text-center py-12 text-gray-500">
        <Newspaper size={32} className="mx-auto mb-3 text-gray-600" />
        <p>No news articles available.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4">
        <div>
          <h2 className="text-sm font-semibold text-white">News Feed</h2>
          <p className="text-2xs text-gray-500 mt-0.5">
            {articles.length} articles · Latest Forex Factory headlines
          </p>
        </div>
        <div className="relative w-full sm:w-64">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            type="text"
            placeholder="Search headlines..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="filter-input pl-8 w-full"
          />
        </div>
      </div>

      {/* Currency tag filters */}
      <div className="flex flex-wrap gap-1.5 mb-4">
        <button
          onClick={() => setActiveTag(null)}
          className={`text-2xs px-2.5 py-1 rounded border transition-colors ${
            activeTag === null
              ? 'bg-emerald-900/40 text-emerald-400 border-emerald-700/40'
              : 'bg-dark-border text-gray-400 border-dark-border hover:text-white'
          }`}
        >
          All
        </button>
        {ALL_TAGS.map(tag => (
          <button
            key={tag}
            onClick={() => setActiveTag(activeTag === tag ? null : tag)}
            className={`text-2xs px-2.5 py-1 rounded border transition-colors ${
              activeTag === tag
                ? 'bg-emerald-900/40 text-emerald-400 border-emerald-700/40'
                : 'bg-dark-border text-gray-400 border-dark-border hover:text-white'
            }`}
          >
            {tag}
          </button>
        ))}
      </div>

      {/* News list */}
      <div className="space-y-3">
        {filteredArticles.map((article, i) => (
          <div key={i} className="card p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1">
                <h3 className="text-sm font-semibold text-white leading-snug">
                  {article.headline}
                </h3>
                {article.snippet && (
                  <p className="text-xs text-gray-400 mt-1.5 leading-relaxed">
                    {article.snippet}
                  </p>
                )}
              </div>
              {article.source_link && (
                <a
                  href={article.source_link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-gray-500 hover:text-emerald-400 transition-colors shrink-0 mt-1"
                  title="Open source article"
                >
                  <ExternalLink size={14} />
                </a>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-2 mt-3">
              {article.timestamp && (
                <span className="text-2xs text-gray-500 font-mono">
                  {formatTimestamp(article.timestamp)}
                </span>
              )}
              <span className={`text-2xs px-2 py-0.5 rounded border ${getImpactBadge(article.impact)}`}>
                {(article.impact || 'medium').toUpperCase()}
              </span>
              {article.currency_tags?.map(tag => (
                <span
                  key={tag}
                  className="text-2xs px-1.5 py-0.5 bg-dark-border rounded text-gray-300 font-mono"
                >
                  {tag}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>

      {filteredArticles.length === 0 && (
        <div className="text-center py-8 text-gray-500 text-sm">
          No articles match your search/filter criteria.
        </div>
      )}
    </div>
  );
}