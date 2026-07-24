import React from 'react';
import { Sparkles, AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';

export default function AISummaryFailed() {
  return (
    <div className="min-h-screen bg-[#f4f5f7] flex items-center justify-center p-4 font-sans">
      <div className="bg-white rounded-xl border border-red-100 shadow-sm overflow-hidden w-full max-w-[640px]">
        <div className="px-5 py-3 border-b border-red-100 bg-red-50/30 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-red-600" />
            <span className="text-sm font-bold text-red-950">AI Ticket Summary</span>
          </div>
          <span className="text-[11px] font-bold text-slate-500 bg-white border border-slate-100 shadow-sm px-2 py-0.5 rounded-full uppercase tracking-wider">
            Provider: OpenRouter · Model: openai/gpt-4o
          </span>
        </div>
        <div className="p-6">
          <div className="flex items-center justify-between">
            <div className="flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-red-500 mt-0.5 shrink-0" />
              <div>
                <h4 className="text-[15px] font-bold text-red-600 mb-1">Analysis failed</h4>
                <p className="text-[14px] text-slate-600">The analysis could not be completed. The worker encountered an unexpected error.</p>
              </div>
            </div>
            <Button size="sm" className="bg-blue-600 hover:bg-blue-700 text-white shadow-none shrink-0 ml-4 font-medium px-4">
              Retry
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}