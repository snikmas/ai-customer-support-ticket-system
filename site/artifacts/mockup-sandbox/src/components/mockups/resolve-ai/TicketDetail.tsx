import React from 'react';
import {
  Search, Bell, Plus, Inbox, Clock, Users, Building, Settings,
  ChevronDown, AlertTriangle, Layers, Lock, Sparkles, Paperclip,
  Image as ImageIcon, ChevronRight, CornerDownRight
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';

export default function TicketDetail() {
  const [aiState, setAiState] = React.useState('Completed');

  return (
    <div className="flex h-screen w-full bg-[#f4f5f7] font-sans text-slate-900 overflow-hidden">
      {/* Sidebar */}
      <aside className="w-[220px] bg-white border-r border-[#e2e4e7] flex flex-col shrink-0 h-full z-10">
        <div className="h-14 flex items-center px-5 border-b border-[#e2e4e7] shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="w-5 h-5 bg-blue-600 rounded-sm"></div>
            <span className="font-semibold text-base tracking-tight text-slate-900">ResolveAI</span>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto py-4 flex flex-col gap-1 px-3">
          <NavItem icon={<Inbox className="w-4 h-4" />} label="All Tickets" active count={247} />
          <NavItem icon={<Layers className="w-4 h-4" />} label="My Tickets" count={12} />
          <NavItem icon={<Clock className="w-4 h-4" />} label="Unassigned" count={8} />
          <NavItem icon={<AlertTriangle className="w-4 h-4 text-red-500" />} label="Overdue" count={3} />
          <div className="my-2 border-t border-[#e2e4e7] mx-2"></div>
          <NavItem icon={<Users className="w-4 h-4" />} label="Users" />
          <NavItem icon={<Building className="w-4 h-4" />} label="Departments" />
          <div className="my-2 border-t border-[#e2e4e7] mx-2"></div>
          <NavItem icon={<Settings className="w-4 h-4" />} label="Settings" />
        </div>
        <div className="p-4 border-t border-[#e2e4e7] bg-slate-50/50 shrink-0">
          <div className="flex items-center gap-3">
            <div className="relative">
              <Avatar className="w-8 h-8 rounded-full border border-[#e2e4e7] shadow-sm">
                <AvatarFallback className="bg-white text-xs text-slate-600 font-semibold">SC</AvatarFallback>
              </Avatar>
              <div className="absolute bottom-0 right-0 w-2.5 h-2.5 bg-green-500 border-2 border-slate-50 rounded-full"></div>
            </div>
            <div className="flex flex-col">
              <span className="text-sm font-semibold text-slate-900 leading-tight">Sarah Chen</span>
              <span className="text-xs text-slate-500 font-medium">Agent</span>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Area */}
      <div className="flex-1 flex flex-col h-full overflow-hidden">
        {/* Topbar */}
        <header className="h-14 bg-white border-b border-[#e2e4e7] flex items-center justify-between px-8 shrink-0 z-10">
          <div className="w-[360px] relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <Input
              placeholder="Search tickets..."
              className="w-full pl-9 bg-[#f4f5f7] border-transparent focus-visible:ring-1 focus-visible:ring-blue-600 shadow-none h-9 text-sm rounded-md"
            />
          </div>
          <div className="flex items-center gap-5">
            <button className="text-slate-500 hover:text-slate-700 relative transition-colors">
              <Bell className="w-5 h-5" />
            </button>
            <div className="w-px h-6 bg-[#e2e4e7]"></div>
            <Button className="h-9 bg-blue-600 hover:bg-blue-700 text-white shadow-none text-sm font-medium gap-2 px-4 rounded-md">
              <Plus className="w-4 h-4" /> Create ticket
            </Button>
          </div>
        </header>

        {/* Content */}
        <main className="flex-1 overflow-auto p-8 custom-scrollbar">
          <div className="max-w-[1100px] mx-auto">
            {/* Breadcrumb */}
            <div className="flex items-center gap-2 text-sm text-slate-500 mb-6 font-medium">
              <button className="hover:text-slate-900 transition-colors">All Tickets</button>
              <ChevronRight className="w-4 h-4 text-slate-400" />
              <span className="text-slate-900 bg-slate-200/50 px-2 py-0.5 rounded">#1042</span>
            </div>

            <div className="flex gap-8 items-start">

              {/* LEFT COLUMN */}
              <div className="w-[66%] shrink-0 flex flex-col gap-7">

                {/* Title */}
                <h1 className="text-2xl font-bold text-slate-900 tracking-tight leading-snug pr-4">
                  Streaming response stops after 30 seconds
                </h1>

                {/* Description Card */}
                <div className="bg-white rounded-xl border border-[#e2e4e7] shadow-sm p-6 relative">
                  <div className="absolute top-6 -left-3.5 bg-[#f4f5f7] p-1 rounded-full border border-[#e2e4e7]">
                    <div className="w-4 h-4 rounded-full bg-slate-200"></div>
                  </div>
                  <p className="text-slate-700 text-[15px] leading-relaxed whitespace-pre-wrap font-medium">
                    When making streaming API calls with stream: true, the response stream abruptly terminates at approximately 30 seconds regardless of response length. This is reproducible across multiple API keys and models. The connection closes with no error — just EOF. Affects GPT-4 and Claude-3 endpoints.
                  </p>
                </div>

                {/* AI Analysis Card */}
                <div className={`bg-white rounded-xl border shadow-sm overflow-hidden ${aiState === 'Failed' ? 'border-red-100' : 'border-indigo-100'}`}>
                  <div className={`px-5 py-3 border-b flex items-center justify-between ${aiState === 'Failed' ? 'border-red-100 bg-red-50/30' : 'border-indigo-100 bg-indigo-50/30'}`}>
                    <div className="flex items-center gap-2">
                      <Sparkles className={`w-4 h-4 ${aiState === 'Failed' ? 'text-red-600' : 'text-indigo-600'}`} />
                      <span className={`text-sm font-bold ${aiState === 'Failed' ? 'text-red-950' : 'text-indigo-950'}`}>AI Ticket Summary</span>
                    </div>
                    <div className="flex items-center gap-2">
                      {/* State Selector for mockup review */}
                      <div className="flex items-center p-0.5 bg-white/50 rounded-lg border border-slate-200/50 mr-4">
                        {['Pending', 'Running', 'Completed', 'Failed'].map(s => (
                          <button
                            key={s}
                            onClick={() => setAiState(s)}
                            className={`px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded ${aiState === s ? 'bg-white shadow-sm text-slate-800' : 'text-slate-500 hover:text-slate-700'}`}
                          >
                            {s}
                          </button>
                        ))}
                      </div>
                      {(aiState === 'Completed' || aiState === 'Running' || aiState === 'Failed') && (
                        <span className="text-[11px] font-bold text-slate-500 bg-white px-2 py-0.5 rounded-full uppercase tracking-wider border border-slate-100 shadow-sm">
                          Provider: OpenRouter · Model: openai/gpt-4o
                        </span>
                      )}
                    </div>
                  </div>

                  {aiState === 'Pending' && (
                    <div className="p-8 flex flex-col items-center justify-center text-center">
                      <Clock className="w-5 h-5 text-slate-400 mb-3" />
                      <h4 className="text-[15px] font-bold text-slate-900 mb-1">Pending analysis</h4>
                      <p className="text-[14px] text-slate-500">Waiting for the background worker to pick up this ticket.</p>
                    </div>
                  )}

                  {aiState === 'Running' && (
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
                  )}

                  {aiState === 'Completed' && (
                    <div className="p-5">
                      <p className="text-sm text-slate-700 leading-relaxed font-medium">
                        The customer is experiencing streaming response termination at exactly 30 seconds, consistent with an upstream proxy timeout. Root cause has been identified as an nginx worker_timeout configuration. Infrastructure team has scheduled a fix for Dec 4, 02:00 UTC — no customer-facing action required.
                      </p>
                      <div className="mt-5 flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <span className="text-xs font-medium text-slate-500">Attempt 2 of 3 · Completed Dec 2 at 14:45</span>
                          <a href="#" className="text-sm text-blue-600 hover:text-blue-800 hover:underline font-medium">View previous analysis</a>
                        </div>
                        <Button variant="outline" size="sm" className="h-7 text-xs shadow-none border-[#e2e4e7] text-slate-600 font-semibold px-3">
                          Run new analysis
                        </Button>
                      </div>
                    </div>
                  )}

                  {aiState === 'Failed' && (
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
                  )}
                </div>

                {/* Activity Tabs */}
                <div className="flex items-center gap-6 border-b border-[#e2e4e7] mt-2">
                  <button className="text-sm font-bold text-blue-600 border-b-2 border-blue-600 pb-3 -mb-[1px]">Activity</button>
                  <button className="text-sm font-semibold text-slate-500 hover:text-slate-800 transition-colors pb-3 border-b-2 border-transparent">Customer Info</button>
                  <button className="text-sm font-semibold text-slate-500 hover:text-slate-800 transition-colors pb-3 border-b-2 border-transparent">Related Issues</button>
                </div>

                {/* Comments Thread */}
                <div className="space-y-5">
                  {/* Public Comment Agent */}
                  <div className="flex gap-4 relative">
                    <Avatar className="w-9 h-9 shrink-0 ring-2 ring-white z-10 shadow-sm mt-1">
                      <AvatarFallback className="bg-blue-100 text-blue-700 text-xs font-bold">JM</AvatarFallback>
                    </Avatar>
                    <div className="flex-1 bg-white border border-blue-100 rounded-xl shadow-sm overflow-hidden relative">
                      <div className="absolute left-0 top-0 bottom-0 w-1 bg-blue-500"></div>
                      <div className="px-5 py-3 border-b border-blue-50 flex items-center justify-between bg-slate-50/50">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-bold text-slate-900">Jake Morris</span>
                          <span className="text-[11px] font-bold text-slate-500 bg-slate-200/60 px-1.5 py-0.5 rounded uppercase tracking-wider">Agent</span>
                        </div>
                        <span className="text-xs font-medium text-slate-500">2h ago</span>
                      </div>
                      <div className="p-5 text-[15px] text-slate-700 leading-relaxed font-medium">
                        I've reproduced this on our end. Looks like it's related to the 30s nginx timeout on the streaming proxy layer. Escalating to infrastructure.
                      </div>
                    </div>
                  </div>

                  {/* Internal Note */}
                  <div className="flex gap-4 relative">
                    <Avatar className="w-9 h-9 shrink-0 ring-2 ring-white z-10 shadow-sm mt-1">
                      <AvatarFallback className="bg-indigo-100 text-indigo-700 text-xs font-bold">PN</AvatarFallback>
                    </Avatar>
                    <div className="flex-1 bg-[#fffbf0] border border-amber-200 rounded-xl shadow-sm overflow-hidden relative">
                      <div className="absolute left-0 top-0 bottom-0 w-1 bg-amber-400"></div>
                      <div className="px-5 py-3 border-b border-amber-100/50 flex items-center justify-between bg-amber-50/50">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-bold text-slate-900">Priya Nair</span>
                          <span className="text-[11px] text-amber-700 bg-amber-100 px-1.5 py-0.5 rounded font-bold flex items-center gap-1 uppercase tracking-wider">
                            <Lock className="w-3 h-3" />
                            Internal Note
                          </span>
                        </div>
                        <span className="text-xs font-medium text-amber-700/60">1h ago</span>
                      </div>
                      <div className="p-5 text-[15px] text-slate-800 leading-relaxed font-medium">
                        Infrastructure confirmed: nginx worker_timeout is set to 30s. Fix is queued for the next deploy window (Dec 4, 02:00 UTC). Monitoring ticket #INF-298.
                      </div>
                    </div>
                  </div>

                  {/* Customer Reply */}
                  <div className="flex gap-4 relative">
                    <Avatar className="w-9 h-9 shrink-0 ring-2 ring-white z-10 shadow-sm mt-1">
                      <AvatarFallback className="bg-slate-200 text-slate-700 text-xs font-bold">AK</AvatarFallback>
                    </Avatar>
                    <div className="flex-1 bg-white border border-[#e2e4e7] rounded-xl shadow-sm overflow-hidden">
                      <div className="px-5 py-3 border-b border-[#e2e4e7]/50 flex items-center justify-between bg-slate-50/50">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-bold text-slate-900">Alex Kim</span>
                          <span className="text-[11px] font-bold text-slate-500 border border-[#e2e4e7] px-1.5 py-0.5 rounded uppercase tracking-wider bg-white">Customer</span>
                        </div>
                        <span className="text-xs font-medium text-slate-500">45m ago</span>
                      </div>
                      <div className="p-5 text-[15px] text-slate-700 leading-relaxed font-medium">
                        Thanks for the update. We're seeing this on all models, not just GPT-4. Any ETA on the fix? This is blocking our production pipeline.
                      </div>
                    </div>
                  </div>
                </div>

                {/* Reply Form */}
                <div className="bg-white rounded-xl border border-blue-200 shadow-sm overflow-hidden mt-4 ring-1 ring-blue-50">
                  <div className="flex border-b border-blue-100 bg-slate-50/30">
                    <button className="px-5 py-3 text-sm font-bold text-blue-700 bg-white border-r border-blue-100 flex items-center gap-2">
                      <CornerDownRight className="w-4 h-4 text-blue-500" /> Public Reply
                    </button>
                    <button className="px-5 py-3 text-sm font-semibold text-slate-500 hover:text-slate-800 hover:bg-slate-50 flex items-center gap-1.5 transition-colors">
                      <Lock className="w-4 h-4 text-slate-400" /> Internal Note
                    </button>
                  </div>
                  <div className="p-4 pb-3">
                    <Textarea
                      rows={4}
                      className="border-none focus-visible:ring-0 shadow-none p-2 resize-none text-[15px] placeholder:text-slate-400 font-medium leading-relaxed"
                      placeholder="Write a reply... (supports Markdown)"
                    />
                    <div className="flex items-center justify-between mt-4 pt-3">
                      <div className="flex gap-1">
                        <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-slate-700 hover:bg-slate-100">
                          <Paperclip className="w-4 h-4" />
                        </Button>
                        <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-slate-700 hover:bg-slate-100">
                          <ImageIcon className="w-4 h-4" />
                        </Button>
                      </div>
                      <Button className="bg-blue-600 hover:bg-blue-700 text-white shadow-none h-9 text-sm px-5 font-semibold">
                        Submit Reply
                      </Button>
                    </div>
                  </div>
                </div>

                {/* Timeline */}
                <div className="bg-white rounded-xl border border-[#e2e4e7] shadow-sm p-6 mt-4 mb-12">
                  <h3 className="text-sm font-bold text-slate-900 mb-6 uppercase tracking-wider">Activity Timeline</h3>
                  <div className="relative pl-4 space-y-5">
                    <div className="absolute left-[19px] top-2 bottom-2 w-[2px] bg-slate-100"></div>

                    <TimelineItem dot="bg-slate-300" text={<span>Ticket created by <span className="font-bold text-slate-900">Alex Kim</span></span>} time="Dec 2, 09:15" />
                    <TimelineItem dot="bg-blue-500" text={<span>Status changed to <span className="font-bold text-slate-900">Open</span></span>} time="Dec 2, 09:18" />
                    <TimelineItem dot="bg-slate-300" text={<span>Assigned to <span className="font-bold text-slate-900">Jake Morris</span></span>} time="Dec 2, 10:30" />
                    <TimelineItem dot="bg-indigo-500" text={<span>Status changed to <span className="font-bold text-slate-900">In progress</span></span>} time="Dec 2, 11:00" />
                    <TimelineItem dot="bg-amber-400" text={<span>Internal note added by <span className="font-bold text-slate-900">Priya Nair</span></span>} time="Dec 2, 14:30" />
                  </div>
                </div>

              </div>

              {/* RIGHT SIDEBAR COLUMN */}
              <div className="w-[34%] shrink-0 space-y-4">

                {/* Agent Actions Block */}
                <div className="bg-white rounded-xl border border-[#e2e4e7] shadow-sm overflow-hidden">
                  <div className="p-5 border-b border-[#e2e4e7] bg-slate-50/50">
                    <div className="flex items-center justify-between mb-4">
                      <span className="text-sm font-bold text-slate-700">Current Status</span>
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-indigo-50 text-indigo-700 border border-indigo-200">
                        In progress
                      </span>
                    </div>
                    <div className="flex flex-col gap-2.5">
                      <Button variant="outline" className="w-full shadow-sm border-[#e2e4e7] text-slate-400 justify-center font-semibold bg-slate-50" disabled>
                        Claim ticket
                      </Button>
                      <Button variant="outline" className="w-full shadow-sm border-[#e2e4e7] text-slate-800 justify-center font-semibold hover:bg-slate-50">
                        Assign agent
                      </Button>
                      <div className="grid grid-cols-2 gap-2.5">
                        <Button variant="outline" className="w-full shadow-sm border-[#e2e4e7] text-slate-400 justify-center font-semibold bg-slate-50" disabled>
                          Start work
                        </Button>
                        <Button variant="outline" className="w-full shadow-sm border-[#e2e4e7] text-slate-800 justify-between font-semibold hover:bg-slate-50 px-3">
                          Change <ChevronDown className="w-4 h-4 text-slate-400 shrink-0" />
                        </Button>
                      </div>
                      <Button variant="outline" className="w-full shadow-sm border-green-200 text-green-700 hover:bg-green-50 hover:text-green-800 font-semibold bg-green-50/30">
                        Resolve
                      </Button>
                    </div>
                  </div>
                </div>

                {/* Ticket Info Block */}
                <div className="bg-white rounded-xl border border-[#e2e4e7] shadow-sm sticky top-6 overflow-hidden">
                  <div className="p-5 border-b border-[#e2e4e7] space-y-3.5">
                    <h3 className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-4">Ticket Info</h3>

                    <div className="flex justify-between items-start">
                      <span className="text-sm font-medium text-slate-500">Priority</span>
                      <div className="flex items-center gap-2 text-sm font-bold text-red-600 bg-red-50 px-2 py-0.5 rounded border border-red-100">
                        <div className="w-2 h-2 rounded-full bg-red-600"></div>
                        Critical
                      </div>
                    </div>
                    <div className="flex justify-between items-start">
                      <span className="text-sm font-medium text-slate-500 pt-0.5">Department</span>
                      <span className="text-sm text-slate-900 font-bold">API Support</span>
                    </div>
                    <div className="flex justify-between items-start">
                      <span className="text-sm font-medium text-slate-500 pt-1">Assignee</span>
                      <div className="flex items-center gap-2">
                        <Avatar className="w-6 h-6 rounded-full border border-slate-200">
                          <AvatarFallback className="bg-slate-100 text-[10px] text-slate-700 font-bold">JM</AvatarFallback>
                        </Avatar>
                        <span className="text-sm text-slate-900 font-bold">Jake Morris</span>
                      </div>
                    </div>
                    <div className="flex justify-between items-start flex-col gap-2.5 pt-2">
                      <span className="text-sm font-medium text-slate-500">Required Skills</span>
                      <div className="flex flex-wrap gap-2">
                        <span className="px-2 py-1 bg-slate-100 text-slate-600 text-xs font-bold rounded border border-slate-200/60">streaming</span>
                        <span className="px-2 py-1 bg-slate-100 text-slate-600 text-xs font-bold rounded border border-slate-200/60">nginx</span>
                        <span className="px-2 py-1 bg-slate-100 text-slate-600 text-xs font-bold rounded border border-slate-200/60">infrastructure</span>
                      </div>
                    </div>

                    <div className="mt-4 pt-4 border-t border-[#e2e4e7] space-y-3.5">
                      <div className="flex justify-between items-start">
                        <span className="text-sm font-medium text-slate-500">Reporter</span>
                        <span className="text-sm text-slate-900 font-bold">Alex Kim</span>
                      </div>
                      <div className="flex justify-between items-start">
                        <span className="text-sm font-medium text-slate-500">Created</span>
                        <span className="text-sm text-slate-900 font-medium">Dec 2, 09:15</span>
                      </div>
                      <div className="flex justify-between items-start">
                        <span className="text-sm font-medium text-slate-500">Updated</span>
                        <span className="text-sm text-slate-900 font-medium">2 minutes ago</span>
                      </div>
                    </div>
                  </div>

                  <div className="p-5">
                    <h3 className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-4">Service Level Agreement</h3>
                    <div className="flex justify-between items-center mb-3">
                      <span className="text-sm font-medium text-slate-500">Deadline</span>
                      <span className="text-sm font-bold text-red-600">Dec 3, 14:00</span>
                    </div>
                    <div className="bg-red-50 border border-red-100 rounded-md p-2.5 flex items-start gap-2.5">
                      <AlertTriangle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
                      <span className="text-sm font-bold text-red-600 leading-tight">Overdue by 4 hours</span>
                    </div>
                  </div>

                </div>

              </div>

            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

function NavItem({ icon, label, active, count }: { icon: React.ReactNode, label: string, active?: boolean, count?: number }) {
  return (
    <button className={`w-full flex items-center justify-between px-3 py-2 rounded-md text-sm transition-colors ${active ? 'bg-blue-50 text-blue-700 font-semibold' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 font-medium'}`}>
      <div className="flex items-center gap-3">
        {icon}
        {label}
      </div>
      {count !== undefined && (
        <span className={`text-xs px-2 py-0.5 rounded-full font-bold ${active ? 'bg-blue-100 text-blue-700' : 'bg-slate-200/70 text-slate-500'}`}>
          {count}
        </span>
      )}
    </button>
  );
}

function TimelineItem({ dot, text, time }: { dot: string, text: React.ReactNode, time: string }) {
  return (
    <div className="relative flex gap-4 text-sm text-slate-600 items-start">
      <div className={`w-2.5 h-2.5 rounded-full ${dot} mt-1.5 ring-[5px] ring-white z-10 shrink-0`}></div>
      <div className="flex-1 font-medium">{text} <span className="text-slate-400 text-xs ml-1 font-medium">· {time}</span></div>
    </div>
  );
}