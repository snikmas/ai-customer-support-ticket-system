import React from 'react';
import { Sparkles } from 'lucide-react';

export default function AISummaryRunning() {
  return (
    <div className="min-h-screen bg-[#f4f5f7] flex items-center justify-center p-4 font-sans">
      <div className="bg-white rounded-xl border border-indigo-100 shadow-sm overflow-hidden w-full max-w-[640px]">
        <div className="px-5 py-3 border-b border-indigo-100 bg-indigo-50/30 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-indigo-600" />
            <span className="text-sm font-bold text-indigo-950">AI Ticket Summary</span>
          </div>
          <span className="text-[11px] font-bold text-slate-500 bg-white border border-slate-100 shadow-sm px-2 py-0.5 rounded-full uppercase tracking-wider">
            Provider: OpenRouter · Model: openai/gpt-4o
          </span>
        </div>
        <div className="p-6">
          <div className="flex items-center gap-2.5 mb-4">
            <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse"></div>
            <span className="text-[15px] font-bold text-slate-800">Analyzing ticket...</span>
          </div>
          <div className="w-full h-1 bg-slate-100 rounded-full overflow-hidden mb-3">
            <div className="h-full bg-blue-500 w-[40%] animate-pulse rounded-full"></div>
          </div>
          <p className="text-[14px] text-slate-500">This runs in the background and may take 30–60 seconds.</p>
        </div>
      </div>
    </div>
  );
}