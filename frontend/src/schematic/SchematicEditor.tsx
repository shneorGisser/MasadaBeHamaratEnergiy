import {
  addEdge,
  Background,
  ConnectionMode,
  Controls,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  ViewportPortal,
  type Connection,
  type Edge,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSelection } from '../selection'
import { api } from '../api/client'
import { ErrorBox } from '../components/ErrorBox'
import ComponentNode from './ComponentNode'
import CurrentEdge, { type CurrentData } from './CurrentEdge'
import PhasorDiagram, { type Phasor } from './PhasorDiagram'
import { useCatalog, useCircuit } from './hooks'
import { useDxfExport } from './useDxfExport'
import { route, routeInput, type Pt } from './router'
import { junctions } from './dxf'
import {
  fromFlow,
  nets,
  newComponent,
  toFlow,
  type CircuitModel,
  type CompNode,
  type ComponentType,
} from './model'

const nodeTypes = { component: ComponentNode }
const edgeTypes = { current: CurrentEdge }

interface LivePoint {
  status: string
  dc?: boolean
  readings?: Record<string, Record<string, number | null>>
  wire_currents?: Record<string, { I: number; angle_deg?: number } | null>
  error?: { message: string }
}

function ParamPanel({
  node,
  onChange,
}: {
  node: CompNode
  onChange: (params: Record<string, unknown>, label: string) => void
}) {
  const { comp, ctype } = node.data
  return (
    <div className="stack" style={{ gap: 8 }} data-testid="param-panel">
      <h3>
        {comp.id} — {ctype?.label_he ?? comp.type}
      </h3>
      <label className="field">
        תווית
        <input className="input" value={comp.label} onChange={(e) => onChange(comp.params, e.target.value)} />
      </label>
      {comp.type === 'transformer3' && <p className="muted small">הפרמטרים נלקחים ממפרט השנאי של הפרויקט (מקור אמת יחיד).</p>}
      {comp.type === 'syncmachine3' && (
        <p className="muted small">פרמטרי המכונה נלקחים ממפרט הפרויקט. כאן נקבעים זרם העירור, מהירות המנוע המניע (כשאין רשת) והספק הציר (כשמחובר לרשת).</p>
      )}
      {comp.type === 'woundmotor3' && (
        <p className="muted small">פרמטרי המכונה מהמפרט. מעגל הרוטור (מתנע, מכשירים) מחובר לטבעות R1–R3; כשהרוטור מסתובב הוא עובד בתדר ההחלקה ואסור לחבר אותו לצד הסטטור.</p>
      )}
      {comp.type === 'dcmachine' && (
        <p className="muted small">פרמטרי המכונה מהמפרט. A1–A2 עוגן, F1–F2 עירור מקבילי, S1–S2 עירור טורי. מנוע: המהירות נקבעת מאיזון המומנטים מול הבלם; מחולל: מנוע הסרוו כופה את המהירות.</p>
      )}
      {comp.type === 'motor3' && (
        <p className="muted small">פרמטרי המנוע נלקחים ממפרט המנוע של הפרויקט. כאן נקבעים רק מומנט הבלם ונעילת הרוטור; ההחלקה נפתרת מאיזון המומנטים.</p>
      )}
      {ctype?.instrument && <p className="muted small">מכשיר אידיאלי: ללא העמסה, ללא שגיאת דיוק.</p>}
      {(ctype?.params ?? []).map((pd) => {
        const v = comp.params[pd.key] ?? pd.default
        if (pd.kind === 'bool')
          return (
            <label key={pd.key} className="row small">
              <input
                type="checkbox"
                name={`param-${pd.key}`}
                checked={Boolean(v)}
                onChange={(e) => onChange({ ...comp.params, [pd.key]: e.target.checked }, comp.label)}
              />
              {pd.label_he}
            </label>
          )
        if (pd.kind === 'choice')
          return (
            <label key={pd.key} className="field">
              {pd.label_he}
              <select
                className="input"
                name={`param-${pd.key}`}
                value={String(v)}
                onChange={(e) => onChange({ ...comp.params, [pd.key]: e.target.value }, comp.label)}
              >
                {pd.choices.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </label>
          )
        return (
          <label key={pd.key} className="field">
            {pd.label_he} {pd.unit && <span className="muted">[{pd.unit}]</span>}
            <input
              className="input num"
              name={`param-${pd.key}`}
              value={String(v)}
              onChange={(e) => {
                const n = Number(e.target.value)
                onChange({ ...comp.params, [pd.key]: e.target.value.trim() === '' || Number.isNaN(n) ? e.target.value : n }, comp.label)
              }}
            />
          </label>
        )
      })}
    </div>
  )
}

function Editor({
  projectId,
  kind,
  circuit,
  catalog,
}: {
  projectId: string
  kind: string
  circuit: CircuitModel
  catalog: ComponentType[]
}) {
  const initial = useMemo(() => toFlow(circuit, catalog), [circuit, catalog])
  const [nodes, setNodes, onNodesChange] = useNodesState<CompNode>(initial.nodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(initial.edges)
  const [dirty, setDirty] = useState(false)
  const exportDxf = useDxfExport()
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<unknown>(null)
  const [saved, setSaved] = useState(false)
  const selected = nodes.find((n) => n.selected)
  const shared = useSelection((st) => st.selected)
  const select = useSelection((st) => st.select)
  const wire = useSelection((st) => st.wire)
  // current flow: the solved current of every cable of the SAVED circuit (display only)
  const [flowOn, setFlowOn] = useState(false)
  const [labelsOn, setLabelsOn] = useState(false)
  const flowQuery = useQuery({
    queryKey: ['current-flow', projectId, kind, circuit],
    queryFn: () => api.post<LivePoint>(`/api/projects/${projectId}/circuits/${kind}/operating-point`, { overrides: {}, wire_currents: true }),
    enabled: flowOn,
  })
  const flow: LivePoint | null = useMemo(
    () => (flowQuery.isError ? { status: 'error', error: { message: String(flowQuery.error) } } : (flowQuery.data ?? null)),
    [flowQuery.isError, flowQuery.error, flowQuery.data],
  )
  const flowBusy = flowQuery.isFetching

  // cables routed around the components; while a node is dragged they fall back to the plain
  // smooth step and are re-routed on release (routing every frame would stutter)
  const dragging = nodes.some((n) => n.dragging)
  const layoutKey = dragging
    ? 'dragging'
    : JSON.stringify([nodes.map((n) => [n.id, n.data.comp.type, Math.round(n.position.x), Math.round(n.position.y)]), edges.map((e) => [e.id, e.source, e.sourceHandle, e.target, e.targetHandle])])
  const routes = useMemo<Map<string, Pt[]> | null>(
    () => (layoutKey === 'dragging' ? null : route(routeInput(fromFlow(nodes, edges), catalog))),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- layoutKey captures what routing depends on
    [layoutKey, catalog],
  )

  // junction dots where three conductors meet (a T): the drawing convention that tells a
  // connection from a crossing
  const dots = useMemo(() => {
    if (!routes) return []
    const input = routeInput(fromFlow(nodes, edges), catalog)
    return junctions({ boxes: [], pins: input.terminals.map((t) => ({ name: t.name, x: t.p[0], y: t.p[1] })), wires: input.wires.map((w) => routes.get(w.id) ?? []) })
    // eslint-disable-next-line react-hooks/exhaustive-deps -- recomputed with the routes
  }, [routes])

  // the cable the wiring guide is on: drawn thick and animated (display only, not saved)
  const shownEdges = useMemo(() => {
    let out: Edge[] = edges.map((e) => ({ ...e, type: 'current', data: { points: routes?.get(e.id) } }))
    const wc = flowOn && !dirty ? flow?.wire_currents : undefined
    if (wc) {
      const scale = Math.max(1e-30, ...Object.values(wc).map((x) => (x ? Math.abs(x.I) : 0)))
      out = out.map((e) => {
        const x = wc[e.id]
        const data: CurrentData = { ...(e.data as CurrentData), I: x ? x.I : null, angle: x?.angle_deg, dc: Boolean(flow?.dc), scale, showLabel: labelsOn }
        return { ...e, type: 'current', data }
      })
    }
    if (wire) out = out.map((e) => (e.id === wire ? { ...e, animated: true, zIndex: 10, style: { stroke: '#c0392b', strokeWidth: 4 } } : e))
    return out
  }, [edges, routes, wire, flowOn, flow, dirty, labelsOn])

  // external selection (3D bench) → schematic
  useEffect(() => {
    setNodes((ns) => {
      const changed = ns.some((n) => Boolean(n.selected) !== (n.id === shared))
      return changed ? ns.map((n) => ({ ...n, selected: n.id === shared })) : ns
    })
  }, [shared, setNodes])

  const markDirty = () => {
    setDirty(true)
    setSaved(false)
  }

  const onConnect = useCallback(
    (c: Connection) => {
      if (c.source === c.target && c.sourceHandle === c.targetHandle) return
      const id = `w${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`
      setEdges((eds) => addEdge({ ...c, id, type: 'smoothstep' }, eds))
      markDirty()
    },
    [setEdges],
  )

  const addComponent = (t: ComponentType) => {
    const comp = newComponent(t, nodes.map((n) => n.id))
    select(comp.id)
    setNodes((ns) => [
      ...ns.map((n) => ({ ...n, selected: false })),
      { id: comp.id, type: 'component', position: { x: 40 + 20 * (ns.length % 10), y: 40 }, data: { comp, ctype: t }, selected: true },
    ])
    markDirty()
  }

  const updateSelected = (params: Record<string, unknown>, label: string) => {
    if (!selected) return
    setNodes((ns) =>
      ns.map((n) => (n.id === selected.id ? { ...n, data: { ...n.data, comp: { ...n.data.comp, params, label } } } : n)),
    )
    markDirty()
  }

  const deleteSelected = () => {
    const ids = new Set(nodes.filter((n) => n.selected).map((n) => n.id))
    setNodes((ns) => ns.filter((n) => !ids.has(n.id)))
    setEdges((es) => es.filter((e) => !e.selected && !ids.has(e.source) && !ids.has(e.target)))
    markDirty()
  }

  const save = async () => {
    setSaving(true)
    setSaveError(null)
    try {
      const doc = fromFlow(nodes, edges)
      await api.put(`/api/projects/${projectId}/circuits/${kind}`, doc)
      setDirty(false)
      setSaved(true)
    } catch (e) {
      setSaveError(e)
    } finally {
      setSaving(false)
    }
  }

  // instrument dials: the live reading of each meter (display only)
  const shownNodes = useMemo(() => {
    const rd = flowOn && !dirty ? flow?.readings : undefined
    if (!rd) return nodes
    const dc = Boolean(flow?.dc)
    return nodes.map((n) => {
      const q = { ammeter: ['I', 'A'], voltmeter: ['U', 'V'], wattmeter: ['P', 'W'] }[n.data.comp.type] as [string, string] | undefined
      const v = q ? rd[n.id]?.[q[0]] : undefined
      if (!q || typeof v !== 'number') return n
      return { ...n, data: { ...n.data, reading: { value: v, unit: q[1], signed: dc || q[0] === 'P' } } }
    })
  }, [nodes, flowOn, dirty, flow])

  // AC only: voltmeter voltages and ammeter currents (current into the ammeter's p terminal)
  const phasors = useMemo<Phasor[]>(() => {
    if (!flowOn || dirty || !flow?.readings || !flow.wire_currents || flow.dc) return []
    const out: Phasor[] = []
    for (const n of nodes) {
      const { comp } = n.data
      if (comp.type === 'voltmeter') {
        const r = flow.readings[comp.id]
        if (typeof r?.U === 'number' && typeof r.angle_deg === 'number') out.push({ label: comp.id, mag: r.U, angle_deg: r.angle_deg, kind: 'U' })
      } else if (comp.type === 'ammeter') {
        const e = edges.find((x) => (x.source === comp.id && x.sourceHandle === 'p') || (x.target === comp.id && x.targetHandle === 'p'))
        const w = e ? flow.wire_currents[e.id] : null
        if (e && w && typeof w.angle_deg === 'number' && w.I > 1e-9) {
          const into = e.target === comp.id // wire current flows source → target
          out.push({ label: comp.id, mag: w.I, angle_deg: w.angle_deg + (into ? 0 : 180), kind: 'I' })
        }
      }
    }
    return out.slice(0, 8)
  }, [flowOn, dirty, flow, nodes, edges])

  const currentNets = useMemo(() => nets(fromFlow(nodes, edges)), [nodes, edges])

  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="row small">
        <span className="muted">הוסף:</span>
        {catalog
          // A machine's parameters come from the project's equipment spec, so only the machine
          // this experiment's circuit already contains is offered.
          .filter((t) => t.category !== 'machine' || circuit.components.some((c) => c.type === t.type))
          .map((t) => (
          <button key={t.type} className="btn small" onClick={() => addComponent(t)} data-testid={`add-${t.type}`}>
            {t.label_he}
          </button>
        ))}
      </div>
      <div className="row">
        <button className="btn primary" onClick={() => void save()} disabled={!dirty || saving} data-testid="save-circuit">
          שמור מעגל
        </button>
        <button className="btn" onClick={() => exportDxf(`circuit-${kind}.dxf`, fromFlow(nodes, edges), catalog, routes)} data-testid="export-dxf" title="AutoCAD R12 — נפתח בכל תוכנת CAD">
          ייצוא DXF
        </button>
        <button className="btn danger" onClick={deleteSelected} disabled={!nodes.some((n) => n.selected) && !edges.some((e) => e.selected)} data-testid="delete-selected">
          מחק נבחר
        </button>
        {dirty && <span className="badge warn" data-testid="dirty">יש שינויים שלא נשמרו — הסימולציה משתמשת במעגל השמור</span>}
        {saved && !dirty && <span className="badge ok">המעגל נשמר</span>}
        <span className="muted small grow">חיבור = גרירה מהדק להדק. קרבה במסך אינה חיבור חשמלי.</span>
      </div>
      <div className="row small" data-testid="flow-controls">
        <label className="row" style={{ gap: 4 }}>
          <input type="checkbox" checked={flowOn} onChange={(e) => setFlowOn(e.target.checked)} data-testid="show-current" />
          הצג זרימת זרם בכבלים
        </label>
        <label className="row" style={{ gap: 4 }}>
          <input type="checkbox" checked={labelsOn} disabled={!flowOn} onChange={(e) => setLabelsOn(e.target.checked)} data-testid="show-current-values" />
          עם ערכים
        </label>
        {flowOn && flowBusy && <span className="muted">פותר…</span>}
        {flowOn && dirty && <span className="badge warn">הזרמים מוצגים אחרי שמירת המעגל</span>}
        {flowOn && flow && flow.status !== 'success' && flow.status !== 'success_with_warnings' && (
          <span className="badge warn" data-testid="flow-error">
            אין פתרון: {flow.error?.message ?? flow.status}
          </span>
        )}
        {flowOn && flow?.wire_currents && !dirty && (
          <span className="muted">
            {flow.dc
              ? 'זרם ישר: הנקודות נעות בכיוון הזרם, במהירות לפי גודלו.'
              : 'זרם חילופין: הנקודות מתנודדות לפי הפאזה (זמן מואט); ערך = RMS.'}{' '}
            נקודת העבודה של המעגל השמור.
          </span>
        )}
      </div>
      {saveError != null && <ErrorBox error={saveError} />}
      <div className="sch-layout">
        <div className="sch-canvas" dir="ltr" data-testid="schematic">
          <ReactFlow
            nodes={shownNodes}
            edges={shownEdges}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            onNodesChange={(ch) => {
              onNodesChange(ch)
              if (ch.some((c) => c.type === 'position' || c.type === 'remove')) markDirty()
            }}
            onEdgesChange={(ch) => {
              onEdgesChange(ch)
              if (ch.some((c) => c.type === 'remove')) markDirty()
            }}
            onConnect={onConnect}
            onNodeClick={(_, n) => select(n.id)}
            onPaneClick={() => select(null)}
            connectionMode={ConnectionMode.Loose}
            fitView
            minZoom={0.2}
            deleteKeyCode={['Delete', 'Backspace']}
          >
            <ViewportPortal>
              <svg style={{ position: 'absolute', left: 0, top: 0, overflow: 'visible', pointerEvents: 'none' }} data-testid="junctions">
                {dots.map(([x, y]) => (
                  <circle key={`${x},${y}`} cx={x} cy={y} r={3.2} fill="#2a3634" />
                ))}
              </svg>
            </ViewportPortal>
            <Background gap={20} />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>
        <aside className="card sch-side">
          {selected ? (
            <ParamPanel node={selected} onChange={updateSelected} />
          ) : (
            <div className="stack" style={{ gap: 6 }}>
              <h3>צמתים חשמליים ({currentNets.length})</h3>
              <ol className="small" style={{ margin: 0, paddingInlineStart: 28, maxHeight: 360, overflow: 'auto' }} data-testid="nets" dir="ltr">
                {currentNets.map((n) => (
                  <li key={n.join()}>{n.join(' · ')}</li>
                ))}
              </ol>
              <PhasorDiagram phasors={phasors} />
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}

export default function SchematicEditor({ projectId, kind }: { projectId: string; kind: string }) {
  const catalog = useCatalog()
  const circuit = useCircuit(projectId, kind)
  if (catalog.isLoading || circuit.isLoading) return <p className="muted">טוען מעגל…</p>
  if (catalog.isError) return <ErrorBox error={catalog.error} />
  if (circuit.isError) return <ErrorBox error={circuit.error} />
  const c = circuit.data?.circuit
  if (!c) return <p className="muted">לניסוי זה אין מעגל עריך.</p>
  return (
    <ReactFlowProvider>
      <Editor key={JSON.stringify(c)} projectId={projectId} kind={kind} circuit={c} catalog={catalog.data ?? []} />
    </ReactFlowProvider>
  )
}
