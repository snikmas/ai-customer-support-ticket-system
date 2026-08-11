import React from 'react';
import {
  Search, Bell, Plus, Inbox, Clock, Users, Building, Settings,
  ChevronDown, AlertTriangle, Layers, X
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';

const tickets = [
  { id: '1042', title: 'Streaming response stops after 30 seconds', priority: 'Critical', status: 'In progress', dept: 'API Support', assignee: 'Sarah Chen', sla: '4h overdue', updated: '2m ago' },
  { id: '1041', title: 'API key rejected after rotation', priority: 'High', status: 'Open', dept: 'Authentication', assignee: 'Jake Morris', sla: 'Dec 3, 14:00', updated: '15m ago' },
  { id: '1040', title: 'RAG retrieval returns unrelated documents', priority: 'High', status: 'In progress', dept: 'RAG Support', assignee: 'Priya Nair', sla: 'Dec 3, 16:00', updated: '1h ago' },
  { id: '1039', title: 'Unexpected rate-limit response on burst traffic', priority: 'Normal', status: 'New', dept: 'API Support', assignee: null, sla: 'Dec 4, 10:00', updated: '3h ago' },
  { id: '1038', title: 'Completion endpoint returns 500 intermittently', priority: 'High', status: 'Pending', dept: 'API Support', assignee: 'Jake Morris', sla: 'Dec 4, 12:00', updated: '5h ago' },
];

export default function CreateTicket() {
  return (
    <div className="relative flex h-screen w-full bg-[#f4f5f7] font-sans text-slate-900 overflow-hidden">
      {/* Background Shell (Dimmed) */}
      <aside className="w-[220px] bg-white border-r border-[#e2e4e7] flex flex-col shrink-0 h-full">
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
        </div>
      </aside>

      <div className="flex-1 flex flex-col h-full overflow-hidden">
        <header className="h-14 bg-white border-b border-[#e2e4e7] flex items-center justify-between px-8 shrink-0">
          <div className="w-[360px] relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <Input
              placeholder="Search tickets..."
              className="w-full pl-9 bg-[#f4f5f7] border-transparent shadow-none h-9 text-sm rounded-md"
              readOnly
            />
          </div>
          <div className="flex items-center gap-5">
            <button className="text-slate-500">
              <Bell className="w-5 h-5" />
            </button>
            <div className="w-px h-6 bg-[#e2e4e7]"></div>
            <Button className="h-9 bg-blue-600 text-white shadow-none text-sm font-medium gap-2 px-4 rounded-md">
              <Plus className="w-4 h-4" /> Create ticket
            </Button>
          </div>
        </header>

        <main className="flex-1 overflow-hidden p-8">
          <div className="max-w-[1200px] mx-auto opacity-70">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <h1 className="text-2xl font-bold text-slate-900 tracking-tight">All Tickets</h1>
                <Badge variant="secondary" className="bg-slate-200/70 text-slate-700 px-2.5 py-0.5 rounded-full font-semibold border-0">
                  247
                </Badge>
              </div>
            </div>

            <div className="bg-white border border-[#e2e4e7] rounded-xl shadow-sm overflow-hidden h-[400px]">
              <Table>
                <TableHeader>
                  <TableRow className="bg-slate-50/80 border-b border-[#e2e4e7]">
                    <TableHead className="w-[80px] text-slate-500 font-semibold text-xs uppercase tracking-wider h-11 pl-5">ID</TableHead>
                    <TableHead className="text-slate-500 font-semibold text-xs uppercase tracking-wider h-11">Title</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {tickets.map((ticket) => (
                    <TableRow key={ticket.id} className="border-b border-[#e2e4e7] h-[52px]">
                      <TableCell className="font-medium text-slate-500 pl-5">#{ticket.id}</TableCell>
                      <TableCell className="font-semibold text-slate-900">{ticket.title}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        </main>
      </div>

      {/* MODAL OVERLAY */}
      <div className="absolute inset-0 bg-slate-900/30 backdrop-blur-[2px] z-50 flex items-center justify-center p-4">
        <div className="w-full max-w-[560px] bg-white rounded-2xl shadow-2xl shadow-slate-900/10 border border-[#e2e4e7] flex flex-col font-sans overflow-hidden animate-in fade-in zoom-in-95 duration-200">

          {/* Modal Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-[#e2e4e7]">
            <h2 className="text-lg font-bold text-slate-900">New Ticket</h2>
            <button className="text-slate-400 hover:text-slate-600 transition-colors p-1 rounded-md hover:bg-slate-100">
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Modal Body */}
          <div className="p-6 flex flex-col gap-6 overflow-y-auto max-h-[calc(100vh-200px)]">

            {/* Title Field (with error state) */}
            <div className="space-y-2">
              <label className="text-sm font-semibold text-slate-900">Title <span className="text-red-500">*</span></label>
              <Input
                placeholder="Brief description of the issue"
                className="border-red-300 focus-visible:ring-1 focus-visible:ring-red-500 shadow-none h-10"
                defaultValue=""
              />
              <div className="flex items-center gap-1.5 mt-1.5 text-red-600 text-sm font-medium">
                <AlertTriangle className="w-3.5 h-3.5" />
                <span>Title is required</span>
              </div>
            </div>

            {/* Description Field */}
            <div className="space-y-2">
              <label className="text-sm font-semibold text-slate-900">Description</label>
              <Textarea
                rows={5}
                placeholder="Provide steps to reproduce, error messages, expected vs actual behavior..."
                className="resize-none border-[#e2e4e7] focus-visible:ring-1 focus-visible:ring-blue-600 shadow-none"
              />
            </div>

            {/* Category Field */}
            <div className="space-y-2">
              <label className="text-sm font-semibold text-slate-900">Category <span className="text-red-500">*</span></label>
              <div className="relative">
                <select className="w-full h-10 pl-3 pr-9 rounded-md border border-[#e2e4e7] bg-white text-sm focus:outline-none focus:ring-1 focus:ring-blue-600 appearance-none shadow-none text-slate-900 font-medium">
                  <option>API Error</option>
                  <option>Authentication</option>
                  <option>Model Output</option>
                  <option>RAG Retrieval</option>
                  <option>Agent Workflow</option>
                  <option>Performance</option>
                  <option>Billing</option>
                  <option>Account Access</option>
                  <option>Documentation</option>
                  <option>Feature Request</option>
                </select>
                <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-slate-400">
                  <ChevronDown className="w-4 h-4" />
                </div>
              </div>
            </div>

            {/* Department Field */}
            <div className="space-y-2">
              <label className="text-sm font-semibold text-slate-900">Department <span className="text-red-500">*</span></label>
              <div className="relative">
                <select className="w-full h-10 pl-3 pr-9 rounded-md border border-[#e2e4e7] bg-white text-sm focus:outline-none focus:ring-1 focus:ring-blue-600 appearance-none shadow-none text-slate-900 font-medium">
                  <option>API Support</option>
                  <option>Authentication</option>
                  <option>Billing</option>
                  <option>RAG Support</option>
                </select>
                <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-slate-400">
                  <ChevronDown className="w-4 h-4" />
                </div>
              </div>
            </div>

            {/* Required Skills Field */}
            <div className="space-y-2">
              <label className="text-sm font-semibold text-slate-900">Required Skills</label>
              <div className="min-h-10 flex flex-wrap items-center gap-2 p-1.5 border border-[#e2e4e7] rounded-md focus-within:border-blue-600 focus-within:ring-1 focus-within:ring-blue-600 bg-white">
                <div className="flex items-center gap-1 bg-slate-100 border border-slate-200 text-slate-700 text-xs font-semibold px-2 py-1 rounded">
                  streaming
                  <X className="w-3 h-3 cursor-pointer hover:text-slate-900" />
                </div>
                <div className="flex items-center gap-1 bg-slate-100 border border-slate-200 text-slate-700 text-xs font-semibold px-2 py-1 rounded">
                  nginx
                  <X className="w-3 h-3 cursor-pointer hover:text-slate-900" />
                </div>
                <input
                  type="text"
                  className="flex-1 min-w-[100px] text-sm bg-transparent border-none focus:outline-none p-1 text-slate-900 placeholder:text-slate-400 font-medium"
                  placeholder="Add skill..."
                />
              </div>
            </div>

            {/* Tags Field */}
            <div className="space-y-2">
              <label className="text-sm font-semibold text-slate-900">Tags</label>
              <div className="min-h-10 flex flex-wrap items-center gap-2 p-1.5 border border-[#e2e4e7] rounded-md focus-within:border-blue-600 focus-within:ring-1 focus-within:ring-blue-600 bg-white">
                <div className="flex items-center gap-1 bg-slate-100 border border-slate-200 text-slate-700 text-xs font-semibold px-2 py-1 rounded">
                  timeout
                  <X className="w-3 h-3 cursor-pointer hover:text-slate-900" />
                </div>
                <div className="flex items-center gap-1 bg-slate-100 border border-slate-200 text-slate-700 text-xs font-semibold px-2 py-1 rounded">
                  production
                  <X className="w-3 h-3 cursor-pointer hover:text-slate-900" />
                </div>
                <input
                  type="text"
                  className="flex-1 min-w-[100px] text-sm bg-transparent border-none focus:outline-none p-1 text-slate-900 placeholder:text-slate-400 font-medium"
                  placeholder="Add tag..."
                />
              </div>
            </div>

            {/* Priority Segmented Control */}
            <div className="space-y-2">
              <label className="text-sm font-semibold text-slate-900">Priority</label>
              <div className="flex p-1 bg-slate-100/80 rounded-lg border border-slate-200/50">
                <button className="flex-1 py-1.5 text-sm font-medium text-slate-600 hover:text-slate-900 rounded-md transition-colors">Low</button>
                <button className="flex-1 py-1.5 text-sm font-medium text-slate-600 hover:text-slate-900 rounded-md transition-colors">Normal</button>
                <button className="flex-1 py-1.5 text-sm font-medium text-slate-600 hover:text-slate-900 rounded-md transition-colors">High</button>
                <button className="flex-1 py-1.5 text-sm font-bold bg-white text-red-600 shadow-sm rounded-md border border-slate-200/80 ring-1 ring-black/5">Critical</button>
              </div>
            </div>
          </div>

          {/* Modal Footer */}
          <div className="px-6 py-4 border-t border-[#e2e4e7] bg-slate-50 flex items-center justify-end gap-3">
            <Button variant="outline" className="shadow-none border-[#e2e4e7] text-slate-700 font-medium hover:bg-slate-100">
              Cancel
            </Button>
            <Button className="bg-blue-600 hover:bg-blue-700 text-white shadow-none font-medium px-5">
              Create Ticket
            </Button>
          </div>
        </div>
      </div>

    </div>
  );
}

function NavItem({ icon, label, active, count }: { icon: React.ReactNode, label: string, active?: boolean, count?: number }) {
  return (
    <div className={`w-full flex items-center justify-between px-3 py-2 rounded-md text-sm ${active ? 'bg-blue-50 text-blue-700 font-semibold' : 'text-slate-600 font-medium'}`}>
      <div className="flex items-center gap-3">
        {icon}
        {label}
      </div>
      {count !== undefined && (
        <span className={`text-xs px-2 py-0.5 rounded-full font-bold ${active ? 'bg-blue-100 text-blue-700' : 'bg-slate-200/70 text-slate-500'}`}>
          {count}
        </span>
      )}
    </div>
  );
}