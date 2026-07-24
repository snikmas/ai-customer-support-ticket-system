import React from 'react';
import {
  Search, Bell, Plus, Inbox, Clock, Users, Building, Settings,
  ChevronDown, AlertTriangle, ChevronLeft, ChevronRight, Layers
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';

const tickets = [
  { id: '1042', title: 'Streaming response stops after 30 seconds', priority: 'Critical', status: 'In progress', dept: 'API Support', assignee: 'Sarah Chen', sla: '4h overdue', updated: '2m ago' },
  { id: '1041', title: 'API key rejected after rotation', priority: 'High', status: 'Open', dept: 'Authentication', assignee: 'Jake Morris', sla: 'Dec 3, 14:00', updated: '15m ago' },
  { id: '1040', title: 'RAG retrieval returns unrelated documents', priority: 'High', status: 'In progress', dept: 'RAG Support', assignee: 'Priya Nair', sla: 'Dec 3, 16:00', updated: '1h ago' },
  { id: '1039', title: 'Unexpected rate-limit response on burst traffic', priority: 'Normal', status: 'New', dept: 'API Support', assignee: null, sla: 'Dec 4, 10:00', updated: '3h ago' },
  { id: '1038', title: 'Completion endpoint returns 500 intermittently', priority: 'High', status: 'Pending', dept: 'API Support', assignee: 'Jake Morris', sla: 'Dec 4, 12:00', updated: '5h ago' },
  { id: '1037', title: 'Embeddings dimension mismatch after model update', priority: 'Normal', status: 'Open', dept: 'RAG Support', assignee: 'Priya Nair', sla: 'Dec 5, 09:00', updated: '1d ago' },
  { id: '1036', title: 'Billing not reflecting usage credits', priority: 'Low', status: 'Pending', dept: 'Billing', assignee: 'Maria Santos', sla: 'Dec 6, 09:00', updated: '2d ago' },
  { id: '1035', title: 'Cannot delete organization API key via dashboard', priority: 'Normal', status: 'Resolved', dept: 'Authentication', assignee: 'Sarah Chen', sla: '—', updated: '3d ago' },
];

export default function TicketList() {
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
              <div className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-red-500 rounded-full border-2 border-white"></div>
            </button>
            <div className="w-px h-6 bg-[#e2e4e7]"></div>
            <Button className="h-9 bg-blue-600 hover:bg-blue-700 text-white shadow-none text-sm font-medium gap-2 px-4 rounded-md">
              <Plus className="w-4 h-4" /> Create ticket
            </Button>
          </div>
        </header>

        {/* Content */}
        <main className="flex-1 overflow-auto p-8 custom-scrollbar">
          <div className="max-w-[1200px] mx-auto">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <h1 className="text-2xl font-bold text-slate-900 tracking-tight">All Tickets</h1>
                <Badge variant="secondary" className="bg-slate-200/70 text-slate-700 hover:bg-slate-200 px-2.5 py-0.5 rounded-full font-semibold shadow-none border-0">
                  247
                </Badge>
              </div>
            </div>

            {/* Filter Bar */}
            <div className="flex items-center gap-3 mb-4">
              <FilterSelect label="Status" value="All" />
              <FilterSelect label="Priority" value="Any" />
              <FilterSelect label="Department" value="Any" />
              <FilterSelect label="Assignee" value="Any" />
            </div>

            {/* Table */}
            <div className="bg-white border border-[#e2e4e7] rounded-xl shadow-sm overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="bg-slate-50/80 hover:bg-slate-50/80 border-b border-[#e2e4e7]">
                    <TableHead className="w-[80px] text-slate-500 font-semibold text-[13px] uppercase tracking-wider h-11 pl-5">ID</TableHead>
                    <TableHead className="text-slate-500 font-semibold text-[13px] uppercase tracking-wider h-11">Title</TableHead>
                    <TableHead className="w-[110px] text-slate-500 font-semibold text-[13px] uppercase tracking-wider h-11">Priority</TableHead>
                    <TableHead className="w-[130px] text-slate-500 font-semibold text-[13px] uppercase tracking-wider h-11">Status</TableHead>
                    <TableHead className="w-[150px] text-slate-500 font-semibold text-[13px] uppercase tracking-wider h-11">Department</TableHead>
                    <TableHead className="w-[150px] text-slate-500 font-semibold text-[13px] uppercase tracking-wider h-11">Assignee</TableHead>
                    <TableHead className="w-[130px] text-slate-500 font-semibold text-[13px] uppercase tracking-wider h-11">SLA Deadline</TableHead>
                    <TableHead className="w-[100px] text-slate-500 font-semibold text-[13px] uppercase tracking-wider h-11 text-right pr-5">Updated</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {tickets.map((ticket, i) => (
                    <TableRow key={ticket.id} className="group cursor-pointer hover:bg-blue-50/40 transition-colors border-b border-[#e2e4e7] relative h-[52px]">
                      <TableCell className="relative font-medium text-slate-500 pl-5 text-[14px]">
                        <div className="absolute left-0 top-0 bottom-0 w-[3px] bg-transparent group-hover:bg-blue-600 transition-colors" />
                        #{ticket.id}
                      </TableCell>
                      <TableCell className="font-semibold text-slate-900 max-w-[300px] truncate overflow-hidden text-[14px]" title={ticket.title}>
                        {ticket.title}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <div className={`w-2 h-2 rounded-full ${getPriorityColor(ticket.priority)}`}></div>
                          <span className={`text-[14px] ${ticket.priority === 'Critical' ? 'text-red-600 font-semibold' : 'text-slate-600 font-medium'}`}>{ticket.priority}</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={ticket.status} />
                      </TableCell>
                      <TableCell className="text-slate-600 text-[14px] font-medium">{ticket.dept}</TableCell>
                      <TableCell className="text-slate-600 text-[14px]">
                        {ticket.assignee ? (
                          <div className="flex items-center gap-2.5">
                            <Avatar className="w-5 h-5 rounded-full ring-1 ring-slate-200">
                              <AvatarFallback className="bg-slate-100 text-[9px] text-slate-600 font-bold">{getInitials(ticket.assignee)}</AvatarFallback>
                            </Avatar>
                            <span className="text-[14px] font-medium">{ticket.assignee.split(' ')[0]}</span>
                          </div>
                        ) : (
                          <span className="text-slate-400 font-medium">—</span>
                        )}
                      </TableCell>
                      <TableCell>
                        {ticket.sla.includes('overdue') ? (
                          <div className="flex items-center gap-1.5 text-red-600 font-semibold text-[14px] bg-red-50/50 w-fit px-1.5 py-0.5 rounded">
                            <AlertTriangle className="w-3.5 h-3.5" />
                            {ticket.sla}
                          </div>
                        ) : (
                          <span className="text-slate-600 text-[14px]">{ticket.sla}</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right text-slate-500 text-[14px] pr-5">{ticket.updated}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              {/* Pagination */}
              <div className="flex items-center justify-between px-5 py-3 border-t border-[#e2e4e7] bg-slate-50/80">
                <span className="text-sm font-medium text-slate-500">Showing 1–8 of 247</span>
                <div className="flex items-center gap-2">
                  <Button variant="outline" size="sm" className="h-8 w-8 p-0 shadow-none border-[#e2e4e7] text-slate-600 hover:text-slate-900 bg-white disabled:opacity-50" disabled>
                    <ChevronLeft className="w-4 h-4" />
                  </Button>
                  <Button variant="outline" size="sm" className="h-8 w-8 p-0 shadow-none border-[#e2e4e7] text-slate-600 hover:text-slate-900 bg-white">
                    <ChevronRight className="w-4 h-4" />
                  </Button>
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

function FilterSelect({ label, value }: { label: string, value: string }) {
  return (
    <button className="flex items-center gap-2 h-8 px-3 rounded-md border border-[#e2e4e7] bg-white text-sm hover:bg-slate-50 transition-colors shadow-sm">
      <span className="text-slate-500 font-medium">{label}:</span>
      <span className="text-slate-900 font-semibold">{value}</span>
      <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
    </button>
  );
}

function getPriorityColor(p: string) {
  if (p === 'Critical') return 'bg-red-600';
  if (p === 'High') return 'bg-orange-500';
  if (p === 'Normal') return 'bg-blue-600';
  return 'bg-slate-400';
}

function StatusBadge({ status }: { status: string }) {
  let style = '';
  switch(status) {
    case 'New': style = 'bg-slate-100 text-slate-700 border-slate-200/60'; break;
    case 'Open': style = 'bg-blue-50 text-blue-700 border-blue-200/60'; break;
    case 'In progress': style = 'bg-indigo-50 text-indigo-700 border-indigo-200/60'; break;
    case 'Pending': style = 'bg-amber-50 text-amber-700 border-amber-200/60'; break;
    case 'Resolved': style = 'bg-slate-100 text-slate-500 border-slate-200/60'; break;
  }
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold border ${style}`}>
      {status}
    </span>
  );
}

function getInitials(name: string) {
  return name.split(' ').map(n => n[0]).join('');
}