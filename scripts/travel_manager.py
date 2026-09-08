"""Small desktop editor for the existing CSV/GPX travel log."""
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import webbrowser

from travel_core import (ROOT, SOURCES, TravelError, config, read_table,
                         load_records, ensure_ids, save_record, delete_record, build)
from add_point import geocode
from publish import publish
from project_lock import project_lock


def open_path(path):
    if os.name == 'nt':
        os.startfile(str(path))
    elif sys.platform == 'darwin':
        subprocess.Popen(['open', str(path)])
    else:
        subprocess.Popen(['xdg-open', str(path)])


class Manager(tk.Tk):
    def __init__(self, root=ROOT):
        super().__init__()
        self.root_path = Path(root)
        self.cfg = config(root)
        self.title('Yatutbuv — travel log')
        self.geometry('1120x700')
        self.minsize(850, 540)
        self.busy = False
        self.jobs = queue.Queue()
        self.buttons = []
        self.style = ttk.Style(self)
        if 'clam' in self.style.theme_names():
            self.style.theme_use('clam')
        self.style.configure('Treeview', rowheight=27)
        self.style.configure('TButton', padding=(10,6))
        bar = ttk.Frame(self, padding=12)
        bar.pack(fill='x')
        for title, action in [('Open map', self.open_map), ('Check data', lambda:self.run_job(lambda:build(self.root_path,check_only=True))),
                              ('Build files', lambda:self.run_job(lambda:build(self.root_path))), ('Publish to GitHub', self.publish_click),
                              ('Output folder', self.open_output), ('Help',lambda:open_path(self.root_path/'README.md'))]:
            b = ttk.Button(bar,text=title,command=action)
            b.pack(side='left',padx=(0,6));self.buttons.append(b)
        ttk.Label(self,text='Edit locally → Build files → Publish. Your existing uMap map stays the viewer.',padding=(14,0,14,10)).pack(anchor='w')
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill='both',expand=True,padx=12)
        self.views={}
        for kind, title in [('points','Places'),('routes','Routes')]:
            frame = ttk.Frame(self.tabs,padding=10)
            self.tabs.add(frame,text=title)
            top = ttk.Frame(frame); top.pack(fill='x',pady=(0,10))
            ttk.Label(top,text='Find:').pack(side='left')
            search=tk.StringVar(); entry=ttk.Entry(top,textvariable=search,width=38)
            entry.pack(side='left',padx=6)
            top=ttk.Frame(frame);top.pack(fill='x',pady=(0,10))
            for label,action in [('Add GPX' if kind=='routes' else 'Add',lambda k=kind:self.edit(k)),('Edit',lambda k=kind:self.edit_selected(k)),
                                 ('Delete',lambda k=kind:self.delete_selected(k))]:
                b=ttk.Button(top,text=label,command=action);b.pack(side='left',padx=3);self.buttons.append(b)
            if kind=='routes':
                b=ttk.Button(top,text='Replace GPX',command=lambda:self.edit_selected('routes',replace=True))
                b.pack(side='left',padx=3);self.buttons.append(b)
                b=ttk.Button(top,text='Re-clean',command=self.reclean_selected)
                b.pack(side='left',padx=3);self.buttons.append(b)
            cols=('name','layer','country','date') if kind=='points' else ('name','mode','date','distance_km','source')
            area=ttk.Frame(frame);area.pack(fill='both',expand=True)
            tree=ttk.Treeview(area,columns=cols,show='headings',selectmode='browse')
            scrollbar=ttk.Scrollbar(area,orient='vertical',command=tree.yview)
            tree.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side='right',fill='y');tree.pack(fill='both',expand=True)
            for col in cols:
                tree.heading(col,text={'distance_km':'km (from GPX)'}.get(col,col.replace('_',' ').title()))
                tree.column(col,width=380 if col=='name' else 115,minwidth=70,stretch=col=='name')
            tree.bind('<Double-1>',lambda e,k=kind:self.edit_selected(k))
            count=ttk.Label(frame);count.pack(anchor='w',pady=(8,0))
            self.views[kind]={'tree':tree,'search':search,'count':count,'columns':cols}
            search.trace_add('write',lambda *a,k=kind:self.filter(k))
        self.status=tk.StringVar(value='Ready. Local changes are backed up before saving.')
        ttk.Label(self,textvariable=self.status,padding=12,wraplength=1050).pack(fill='x')
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.refresh()
        self.after(100,self.poll_jobs)

    def refresh(self):
        _,self.records,_=load_records(self.root_path)
        for kind in self.views:
            self.filter(kind)

    def filter(self,kind):
        view=self.views[kind];tree=view['tree'];selected=tree.selection()
        tree.delete(*tree.get_children())
        query=view['search'].get().casefold()
        rows=[r for r in self.records[kind] if query in ' '.join(str(v) for k,v in r.items() if not k.startswith('_')).casefold()]
        rows.sort(key=lambda r:(r.get('name','').casefold(),r.get('date','')))
        for r in rows:
            values=[f'{r["_km"]:.1f}' if c=='distance_km' else r.get(c,'') for c in view['columns']]
            tree.insert('', 'end', iid=r['id'], values=values)
        if selected and tree.exists(selected[0]):
            tree.selection_set(selected[0])
        view['count'].configure(text=f'{len(rows)} of {len(self.records[kind])} records')

    def selected(self,kind):
        ids=self.views[kind]['tree'].selection()
        if not ids:
            messagebox.showinfo('Select a record','Select a row first.',parent=self)
            return None
        return next(r for r in self.records[kind] if r['id']==ids[0])

    def edit_selected(self,kind,replace=False):
        if self.busy:return
        row=self.selected(kind)
        if row:self.edit(kind,row,replace)

    def edit(self,kind,row=None,replace=False):
        if not self.busy:Editor(self,kind,row,replace)

    def reclean_selected(self):
        if self.busy:return
        row=self.selected('routes')
        if not row:return
        folder='routes_original' if row.get('original_file') else 'routes'
        path=self.root_path/'data'/folder/(row.get('original_file') or row['file'])
        if not path.exists():
            messagebox.showerror('Original missing','Restore the archived original or use Replace GPX with your complete GPX.',parent=self)
            return
        editor=Editor(self,'routes',row)
        editor.new_gpx=str(path)
        editor.detail_box.configure(state='readonly')
        editor.file_label.configure(text='Re-clean from saved original' if row.get('original_file') else 'Archive and clean existing GPX')

    def delete_selected(self,kind):
        if self.busy:return
        row=self.selected(kind)
        if row and messagebox.askyesno('Delete record',f'Delete {row["name"]}?\nA local backup will be kept.',parent=self):
            try:
                delete_record(kind,row['id'],self.root_path);self.refresh()
                self.status.set('Deleted locally. Build and publish when ready.')
            except Exception as e:messagebox.showerror('Could not delete',str(e),parent=self)

    def open_map(self):webbrowser.open(self.cfg['map_url'])

    def open_output(self):
        target=self.root_path/'exports'
        if not target.exists():messagebox.showinfo('Build first','Use Build files to prepare the local uMap export.',parent=self)
        else:open_path(target)

    def publish_click(self):
        if messagebox.askyesno('Publish current data','Build and push your current travel data to the existing Git repository?\n\nuMap updates automatically only when its layers use the hosted GeoJSON files.',parent=self):
            self.run_job(lambda:publish(self.root_path))

    def run_job(self,action):
        if self.busy:return
        self.busy=True
        for b in self.buttons:b.state(['disabled'])
        self.status.set('Working…')
        def worker():
            try:self.jobs.put((True,action()))
            except Exception as e:self.jobs.put((False,str(e)))
        threading.Thread(target=worker,daemon=True).start()

    def poll_jobs(self):
        try:
            ok,result=self.jobs.get_nowait()
            self.busy=False
            for b in self.buttons:b.state(['!disabled'])
            self.status.set(result if ok else 'Stopped. See the error message.')
            if not ok:messagebox.showerror('Operation stopped',result,parent=self)
        except queue.Empty:pass
        self.after(100,self.poll_jobs)

    def close(self):
        if self.busy:
            messagebox.showinfo('Operation in progress','Please wait for the current operation to finish.',parent=self)
            return
        self.destroy()


class Editor(tk.Toplevel):
    def __init__(self,app,kind,row=None,replace=False):
        super().__init__(app)
        self.app,self.kind,self.row=app,kind,row
        self.title(('Edit ' if row else 'Add ') + ('place' if kind=='points' else 'route'))
        self.transient(app);self.grab_set();self.resizable(True,False)
        self.fields={};self.new_gpx=None
        frame=ttk.Frame(self,padding=16);frame.pack(fill='both',expand=True);frame.columnconfigure(1,weight=1)
        names=['name','layer','country','lat','lon','date','description','color'] if kind=='points' else ['name','mode','date','notes','source']
        labels={'lat':'Latitude','lon':'Longitude','date':'Date (year or YYYY-MM-DD)','source':'Route accuracy','color':'Colour (optional)'}
        for i,name in enumerate(names):
            ttk.Label(frame,text=labels.get(name,name.title())).grid(row=i,column=0,sticky='w',padx=(0,14),pady=5)
            value=(row or {}).get(name,'')
            choices=app.cfg['point_layers'] if name=='layer' else app.cfg['route_modes'] if name=='mode' else SOURCES if name=='source' else None
            if not value and name in ('layer','mode'):value='Places' if name=='layer' else 'drive'
            var=tk.StringVar(value=value);self.fields[name]=var
            widget=ttk.Combobox(frame,textvariable=var,values=choices,state='readonly',width=54) if choices else ttk.Entry(frame,textvariable=var,width=57)
            widget.grid(row=i,column=1,sticky='ew',pady=5)
        n=len(names)
        if kind=='routes':
            self.file_label=ttk.Label(frame,text=(row or {}).get('file','Choose a GPX file.'),wraplength=440)
            self.file_label.grid(row=n,column=1,sticky='w',pady=5)
            ttk.Button(frame,text='Choose GPX…',command=self.choose_gpx).grid(row=n,column=0,sticky='w')
            ttk.Label(frame,text='Map detail').grid(row=n+1,column=0,sticky='w',pady=5)
            self.detail=tk.StringVar(value='Standard')
            self.detail_box=ttk.Combobox(frame,textvariable=self.detail,values=['Standard','Fine','All points'],state='disabled' if row else 'readonly')
            self.detail_box.grid(row=n+1,column=1,sticky='ew')
            stats=''
            if row:
                stats=f"Original distance: {row.get('distance_km','')} km | Elevation: {row.get('min_altitude_m') or '?'} to {row.get('max_altitude_m') or '?'} m"
                if row.get('original_points'):
                    stats+=f"\nPoints: {row['original_points']} original / {row.get('map_points','?')} map"
            ttk.Label(frame,text=stats,wraplength=540).grid(row=n+2,column=0,columnspan=2,sticky='w',pady=5)
            n+=1
        else:
            self.lookup_button=ttk.Button(frame,text='Find coordinates…',command=self.lookup)
            self.lookup_button.grid(row=n,column=0,columnspan=2,sticky='w',pady=6)
            ttk.Label(frame,text='Uses the name and optional country. Choose a result before coordinates are filled in.\nYou can also enter coordinates directly.',wraplength=550).grid(row=n+1,column=0,columnspan=2,sticky='w')
        buttons=ttk.Frame(frame);buttons.grid(row=n+2,column=0,columnspan=2,sticky='e',pady=(16,0))
        ttk.Button(buttons,text='Cancel',command=self.destroy).pack(side='left',padx=6)
        ttk.Button(buttons,text='Save locally',command=self.save).pack(side='left')
        if replace:self.after(100,self.choose_gpx)

    def choose_gpx(self):
        path=filedialog.askopenfilename(parent=self,title='Choose the complete journey GPX',filetypes=[('GPX tracks','*.gpx'),('All files','*.*')])
        if path:
            self.new_gpx=path;self.file_label.configure(text=Path(path).name)
            self.detail_box.configure(state='readonly')
            if not self.fields['name'].get():self.fields['name'].set(Path(path).stem)

    def lookup(self):
        query=self.fields['name'].get().strip()
        if not query:
            messagebox.showinfo('Enter a name','Enter a place name first.',parent=self);return
        country=self.fields['country'].get().strip()
        self.lookup_button.state(['disabled'])
        self.lookup_button.configure(text='Searching…')
        results=queue.Queue()
        def work():
            try:results.put((True,geocode(query,country)))
            except Exception as e:results.put((False,str(e)))
        threading.Thread(target=work,daemon=True).start()
        def poll():
            if not self.winfo_exists():return
            try:ok,hits=results.get_nowait()
            except queue.Empty:self.after(100,poll);return
            self.lookup_button.state(['!disabled']);self.lookup_button.configure(text='Find coordinates…')
            if not ok:messagebox.showerror('Lookup failed',hits,parent=self);return
            if not hits:messagebox.showinfo('No results','Try a more specific name or enter coordinates.',parent=self);return
            picker=tk.Toplevel(self);picker.title('Choose the correct place');picker.transient(self);picker.grab_set()
            box=tk.Listbox(picker,width=110,height=min(8,len(hits)+1),exportselection=False)
            box.pack(padx=12,pady=12)
            for hit in hits:box.insert('end',hit['display_name'])
            def choose():
                if not box.curselection():return
                h=hits[box.curselection()[0]]
                self.fields['lat'].set(h['lat']);self.fields['lon'].set(h['lon'])
                self.fields['country'].set(h.get('address',{}).get('country_code','').upper())
                picker.destroy();self.grab_set()
            def cancel():picker.destroy();self.grab_set()
            ttk.Button(picker,text='Use selected place',command=choose).pack(pady=(0,12))
            picker.protocol('WM_DELETE_WINDOW',cancel)
        self.after(100,poll)

    def save(self):
        try:
            values={k:v.get() for k,v in self.fields.items()}
            if 'country' in values:values['country']=values['country'].upper()
            tolerance=None
            if self.kind=='routes':
                tolerance={'Standard':self.app.cfg['simplify_degrees'],'Fine':self.app.cfg['simplify_degrees']/5,'All points':0}[self.detail.get()]
            rid=save_record(self.kind,values,self.app.root_path,record_id=self.row['id'] if self.row else None,gpx=self.new_gpx,tolerance=tolerance)
            self.app.refresh();self.app.status.set('Saved locally. Build and publish when ready.');self.destroy()
            if self.kind=='routes' and self.new_gpx:
                saved=next(r for r in self.app.records['routes'] if r['id']==rid)
                messagebox.showinfo('Route imported',f"Original archived unchanged.\nPoints: {saved['original_points']} -> {saved['map_points']}\nDistance: {float(saved['distance_km']):.1f} km\nElevation: {saved['min_altitude_m'] or 'unknown'} to {saved['max_altitude_m'] or 'unknown'} m\n\nBuild and publish when ready.",parent=self.app)
        except Exception as e:messagebox.showerror('Could not save',str(e),parent=self)


def main():
    try:
        with project_lock(ROOT):
            ensure_ids()
            app=Manager()
            app.mainloop()
    except Exception as e:
        try:
            window=tk.Tk();window.withdraw()
            messagebox.showerror('Could not open travel log',str(e));window.destroy()
        except tk.TclError:print(f'ERROR: {e}',file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':sys.exit(main())
