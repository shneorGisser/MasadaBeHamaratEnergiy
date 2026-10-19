import {
  addEdge,
  Background,
  ConnectionMode,
  Controls,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSelection } from '../selection'
import { api } from '../api/client'
import { ErrorBox } from '../components/ErrorBox'
import ComponentNode from './ComponentNode'
import { useCatalog, useCircuit } from './hooks'
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
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<unknown>(null)
  const [saved, setSaved] = useState(false)
  const selected = nodes.find((n) => n.selected)
  const shared = useSelection((st) => st.selected)
  const select = useSelection((st) => st.select)

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
        <button className="btn danger" onClick={deleteSelected} disabled={!nodes.some((n) => n.selected) && !edges.some((e) => e.selected)} data-testid="delete-selected">
          מחק נבחר
        </button>
        {dirty && <span className="badge warn" data-testid="dirty">יש שינויים שלא נשמרו — הסימולציה משתמשת במעגל השמור</span>}
        {saved && !dirty && <span className="badge ok">המעגל נשמר</span>}
        <span className="muted small grow">חיבור = גרירה מהדק להדק. קרבה במסך אינה חיבור חשמלי.</span>
      </div>
      {saveError != null && <ErrorBox error={saveError} />}
      <div className="sch-layout">
        <div className="sch-canvas" dir="ltr" data-testid="schematic">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
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
              <ol className="small" style={{ margin: 0, paddingInlineStart: 18, maxHeight: 360, overflow: 'auto' }} data-testid="nets" dir="ltr">
                {currentNets.map((n) => (
                  <li key={n.join()}>{n.join(' · ')}</li>
                ))}
              </ol>
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
