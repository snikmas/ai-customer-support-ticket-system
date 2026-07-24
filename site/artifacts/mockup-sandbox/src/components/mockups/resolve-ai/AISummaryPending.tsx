import React from 'react';
import { Sparkles, Clock } from 'lucide-react';

export default function AISummaryPending() {
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
        <div className="p-8 flex flex-col items-center justify-center text-center">
          <Clock className="w-5 h-5 text-slate-400 mb-3" />
          <h4 className="text-[15px] font-bold text-slate-900 mb-1">Pending analysis</h4>
          <p className="text-[14px] text-slate-500">Waiting for the background worker to pick up this ticket.</p>
        </div>
      </div>
    </div>
  );
}