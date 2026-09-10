// pstack fleet log hook (optional).
//
// Logs every `task` delegation so the fleet board has a timestamped trail
// next to the live dashboard (script/pstack-fleet.py). Deliberately tiny
// and defensive: any failure is swallowed so the plugin can never break
// a session.
//
// Install: copy to `.opencode/plugins/` (project) or
// `~/.config/opencode/plugins/` (global). See FLEET.md.
export const PstackFleet = async ({ client }) => {
  const log = async (message, extra) => {
    try {
      await client.app.log({
        body: { service: "pstack-fleet", level: "info", message, extra },
      })
    } catch {
      // never break the session over observability
    }
  }

  return {
    "tool.execute.after": async (input, output) => {
      try {
        if (input?.tool === "task") {
          const sub = output?.args?.subagent ?? output?.args?.agent ?? "?"
          await log(`fleet: task delegated to ${sub}`, { subagent: String(sub) })
        }
      } catch {
        // never break the session over observability
      }
    },
  }
}
