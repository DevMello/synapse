export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  // Allows to automatically instantiate createClient with right options
  // instead of createClient<Database, { PostgrestVersion: 'XX' }>(URL, KEY)
  __InternalSupabase: {
    PostgrestVersion: "14.5"
  }
  public: {
    Tables: {
      agent_capabilities: {
        Row: {
          agent_id: string
          attached_at: string
          attached_by: string | null
          auto_attached: boolean
          daemon_capability_id: string
          enabled: boolean
          id: string
          org_id: string
        }
        Insert: {
          agent_id: string
          attached_at?: string
          attached_by?: string | null
          auto_attached?: boolean
          daemon_capability_id: string
          enabled?: boolean
          id?: string
          org_id: string
        }
        Update: {
          agent_id?: string
          attached_at?: string
          attached_by?: string | null
          auto_attached?: boolean
          daemon_capability_id?: string
          enabled?: boolean
          id?: string
          org_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "agent_capabilities_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: false
            referencedRelation: "agent_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agent_capabilities_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: false
            referencedRelation: "agents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agent_capabilities_attached_by_fkey"
            columns: ["attached_by"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agent_capabilities_daemon_capability_id_fkey"
            columns: ["daemon_capability_id"]
            isOneToOne: false
            referencedRelation: "daemon_capabilities"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agent_capabilities_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
        ]
      }
      agent_chain_grants: {
        Row: {
          chain_budget_usd: number
          created_at: string
          daemon_id: string
          edges: Json
          expires_at: string
          flow_id: string | null
          granted_by: string | null
          id: string
          key_id: string | null
          max_hops: number
          max_payload_bytes: number
          modes: string[]
          org_id: string
          revoked_at: string | null
          routing: string
          signature: string | null
        }
        Insert: {
          chain_budget_usd?: number
          created_at?: string
          daemon_id: string
          edges?: Json
          expires_at: string
          flow_id?: string | null
          granted_by?: string | null
          id?: string
          key_id?: string | null
          max_hops?: number
          max_payload_bytes?: number
          modes?: string[]
          org_id: string
          revoked_at?: string | null
          routing?: string
          signature?: string | null
        }
        Update: {
          chain_budget_usd?: number
          created_at?: string
          daemon_id?: string
          edges?: Json
          expires_at?: string
          flow_id?: string | null
          granted_by?: string | null
          id?: string
          key_id?: string | null
          max_hops?: number
          max_payload_bytes?: number
          modes?: string[]
          org_id?: string
          revoked_at?: string | null
          routing?: string
          signature?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "agent_chain_grants_daemon_id_fkey"
            columns: ["daemon_id"]
            isOneToOne: false
            referencedRelation: "daemon_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agent_chain_grants_daemon_id_fkey"
            columns: ["daemon_id"]
            isOneToOne: false
            referencedRelation: "daemons"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agent_chain_grants_flow_id_fkey"
            columns: ["flow_id"]
            isOneToOne: false
            referencedRelation: "agent_flows"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agent_chain_grants_granted_by_fkey"
            columns: ["granted_by"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agent_chain_grants_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
        ]
      }
      agent_flows: {
        Row: {
          created_at: string
          created_by: string | null
          daemon_id: string | null
          edges: Json
          id: string
          name: string
          nodes: Json
          org_id: string
          published_grant_id: string | null
          settings: Json
          status: string
          updated_at: string
          version: number
        }
        Insert: {
          created_at?: string
          created_by?: string | null
          daemon_id?: string | null
          edges?: Json
          id?: string
          name?: string
          nodes?: Json
          org_id: string
          published_grant_id?: string | null
          settings?: Json
          status?: string
          updated_at?: string
          version?: number
        }
        Update: {
          created_at?: string
          created_by?: string | null
          daemon_id?: string | null
          edges?: Json
          id?: string
          name?: string
          nodes?: Json
          org_id?: string
          published_grant_id?: string | null
          settings?: Json
          status?: string
          updated_at?: string
          version?: number
        }
        Relationships: [
          {
            foreignKeyName: "agent_flows_created_by_fkey"
            columns: ["created_by"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agent_flows_daemon_id_fkey"
            columns: ["daemon_id"]
            isOneToOne: false
            referencedRelation: "daemon_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agent_flows_daemon_id_fkey"
            columns: ["daemon_id"]
            isOneToOne: false
            referencedRelation: "daemons"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agent_flows_grant_fk"
            columns: ["published_grant_id"]
            isOneToOne: false
            referencedRelation: "agent_chain_grants"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agent_flows_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
        ]
      }
      agent_identities: {
        Row: {
          agent_id: string
          created_at: string
          id: string
          org_id: string
          public_key: string | null
          rotated_at: string | null
        }
        Insert: {
          agent_id: string
          created_at?: string
          id?: string
          org_id: string
          public_key?: string | null
          rotated_at?: string | null
        }
        Update: {
          agent_id?: string
          created_at?: string
          id?: string
          org_id?: string
          public_key?: string | null
          rotated_at?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "agent_identities_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: true
            referencedRelation: "agent_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agent_identities_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: true
            referencedRelation: "agents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agent_identities_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
        ]
      }
      agent_memory: {
        Row: {
          agent_id: string
          bytes: number
          embedding_ref: string | null
          id: string
          key: string
          namespace: string
          org_id: string
          tags: string[]
          text_redacted: string | null
          updated_at: string
          updated_by: string | null
          value_redacted: Json | null
          version: number
        }
        Insert: {
          agent_id: string
          bytes?: number
          embedding_ref?: string | null
          id?: string
          key: string
          namespace?: string
          org_id: string
          tags?: string[]
          text_redacted?: string | null
          updated_at?: string
          updated_by?: string | null
          value_redacted?: Json | null
          version?: number
        }
        Update: {
          agent_id?: string
          bytes?: number
          embedding_ref?: string | null
          id?: string
          key?: string
          namespace?: string
          org_id?: string
          tags?: string[]
          text_redacted?: string | null
          updated_at?: string
          updated_by?: string | null
          value_redacted?: Json | null
          version?: number
        }
        Relationships: [
          {
            foreignKeyName: "agent_memory_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: false
            referencedRelation: "agent_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agent_memory_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: false
            referencedRelation: "agents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agent_memory_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
        ]
      }
      agent_memory_rollups: {
        Row: {
          agent_id: string
          entry_count: number
          org_id: string
          provider: string | null
          total_bytes: number
          updated_at: string
        }
        Insert: {
          agent_id: string
          entry_count?: number
          org_id: string
          provider?: string | null
          total_bytes?: number
          updated_at?: string
        }
        Update: {
          agent_id?: string
          entry_count?: number
          org_id?: string
          provider?: string | null
          total_bytes?: number
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "agent_memory_rollups_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: true
            referencedRelation: "agent_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agent_memory_rollups_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: true
            referencedRelation: "agents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agent_memory_rollups_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
        ]
      }
      agent_orchestration_grants: {
        Row: {
          agent_id: string
          created_at: string
          daemon_id: string
          expires_at: string
          granted_by: string | null
          id: string
          key_id: string | null
          max_depth: number
          max_fan_out: number
          org_id: string
          protected_fields: string[]
          revoked_at: string | null
          signature: string | null
          target_allow: string[]
          tree_budget_usd: number
          verbs: string[]
        }
        Insert: {
          agent_id: string
          created_at?: string
          daemon_id: string
          expires_at: string
          granted_by?: string | null
          id?: string
          key_id?: string | null
          max_depth?: number
          max_fan_out?: number
          org_id: string
          protected_fields?: string[]
          revoked_at?: string | null
          signature?: string | null
          target_allow?: string[]
          tree_budget_usd?: number
          verbs?: string[]
        }
        Update: {
          agent_id?: string
          created_at?: string
          daemon_id?: string
          expires_at?: string
          granted_by?: string | null
          id?: string
          key_id?: string | null
          max_depth?: number
          max_fan_out?: number
          org_id?: string
          protected_fields?: string[]
          revoked_at?: string | null
          signature?: string | null
          target_allow?: string[]
          tree_budget_usd?: number
          verbs?: string[]
        }
        Relationships: [
          {
            foreignKeyName: "agent_orchestration_grants_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: false
            referencedRelation: "agent_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agent_orchestration_grants_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: false
            referencedRelation: "agents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agent_orchestration_grants_daemon_id_fkey"
            columns: ["daemon_id"]
            isOneToOne: false
            referencedRelation: "daemon_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agent_orchestration_grants_daemon_id_fkey"
            columns: ["daemon_id"]
            isOneToOne: false
            referencedRelation: "daemons"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agent_orchestration_grants_granted_by_fkey"
            columns: ["granted_by"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agent_orchestration_grants_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
        ]
      }
      agent_skills: {
        Row: {
          agent_id: string
          bytes: number
          created_at: string
          id: string
          name: string
          org_id: string
          scope: string | null
        }
        Insert: {
          agent_id: string
          bytes?: number
          created_at?: string
          id?: string
          name: string
          org_id: string
          scope?: string | null
        }
        Update: {
          agent_id?: string
          bytes?: number
          created_at?: string
          id?: string
          name?: string
          org_id?: string
          scope?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "agent_skills_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: false
            referencedRelation: "agent_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agent_skills_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: false
            referencedRelation: "agents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agent_skills_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
        ]
      }
      agent_versions: {
        Row: {
          agent_id: string
          author_user_id: string | null
          config: Json
          created_at: string
          id: string
          message: string | null
          org_id: string
          prompt: string | null
          tags: string[]
          version: number
        }
        Insert: {
          agent_id: string
          author_user_id?: string | null
          config?: Json
          created_at?: string
          id?: string
          message?: string | null
          org_id: string
          prompt?: string | null
          tags?: string[]
          version: number
        }
        Update: {
          agent_id?: string
          author_user_id?: string | null
          config?: Json
          created_at?: string
          id?: string
          message?: string | null
          org_id?: string
          prompt?: string | null
          tags?: string[]
          version?: number
        }
        Relationships: [
          {
            foreignKeyName: "agent_versions_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: false
            referencedRelation: "agent_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agent_versions_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: false
            referencedRelation: "agents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agent_versions_author_user_id_fkey"
            columns: ["author_user_id"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agent_versions_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
        ]
      }
      agents: {
        Row: {
          created_at: string
          current_version: number | null
          daemon_id: string | null
          id: string
          limits: Json
          name: string
          org_id: string
          platform: string | null
          status: Database["public"]["Enums"]["agent_status"]
          type: Database["public"]["Enums"]["agent_type"]
          updated_at: string
        }
        Insert: {
          created_at?: string
          current_version?: number | null
          daemon_id?: string | null
          id?: string
          limits?: Json
          name: string
          org_id: string
          platform?: string | null
          status?: Database["public"]["Enums"]["agent_status"]
          type: Database["public"]["Enums"]["agent_type"]
          updated_at?: string
        }
        Update: {
          created_at?: string
          current_version?: number | null
          daemon_id?: string | null
          id?: string
          limits?: Json
          name?: string
          org_id?: string
          platform?: string | null
          status?: Database["public"]["Enums"]["agent_status"]
          type?: Database["public"]["Enums"]["agent_type"]
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "agents_daemon_id_fkey"
            columns: ["daemon_id"]
            isOneToOne: false
            referencedRelation: "daemon_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agents_daemon_id_fkey"
            columns: ["daemon_id"]
            isOneToOne: false
            referencedRelation: "daemons"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agents_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
        ]
      }
      anomaly_events: {
        Row: {
          agent_id: string | null
          baseline: number | null
          created_at: string
          daemon_id: string | null
          detail: Json
          detector: string
          id: string
          metric: string | null
          observed: number | null
          org_id: string
          severity: Database["public"]["Enums"]["anomaly_severity"]
        }
        Insert: {
          agent_id?: string | null
          baseline?: number | null
          created_at?: string
          daemon_id?: string | null
          detail?: Json
          detector: string
          id?: string
          metric?: string | null
          observed?: number | null
          org_id: string
          severity?: Database["public"]["Enums"]["anomaly_severity"]
        }
        Update: {
          agent_id?: string | null
          baseline?: number | null
          created_at?: string
          daemon_id?: string | null
          detail?: Json
          detector?: string
          id?: string
          metric?: string | null
          observed?: number | null
          org_id?: string
          severity?: Database["public"]["Enums"]["anomaly_severity"]
        }
        Relationships: [
          {
            foreignKeyName: "anomaly_events_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: false
            referencedRelation: "agent_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "anomaly_events_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: false
            referencedRelation: "agents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "anomaly_events_daemon_id_fkey"
            columns: ["daemon_id"]
            isOneToOne: false
            referencedRelation: "daemon_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "anomaly_events_daemon_id_fkey"
            columns: ["daemon_id"]
            isOneToOne: false
            referencedRelation: "daemons"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "anomaly_events_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
        ]
      }
      audit_events: {
        Row: {
          action: string
          actor: string | null
          created_at: string
          detail: Json
          hash: string | null
          id: string
          org_id: string
          prev_hash: string | null
          resource_id: string | null
          resource_type: string | null
          run_id: string | null
        }
        Insert: {
          action: string
          actor?: string | null
          created_at?: string
          detail?: Json
          hash?: string | null
          id?: string
          org_id: string
          prev_hash?: string | null
          resource_id?: string | null
          resource_type?: string | null
          run_id?: string | null
        }
        Update: {
          action?: string
          actor?: string | null
          created_at?: string
          detail?: Json
          hash?: string | null
          id?: string
          org_id?: string
          prev_hash?: string | null
          resource_id?: string | null
          resource_type?: string | null
          run_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "audit_events_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "audit_events_run_id_fkey"
            columns: ["run_id"]
            isOneToOne: false
            referencedRelation: "runs"
            referencedColumns: ["id"]
          },
        ]
      }
      daemon_capabilities: {
        Row: {
          args: Json
          created_at: string
          daemon_id: string
          endpoint: string | null
          exposed_tools: string[]
          id: string
          install_status: Database["public"]["Enums"]["capability_status"]
          kind: Database["public"]["Enums"]["capability_kind"]
          org_id: string
          plugin_id: string | null
          plugin_version: string | null
          updated_at: string
        }
        Insert: {
          args?: Json
          created_at?: string
          daemon_id: string
          endpoint?: string | null
          exposed_tools?: string[]
          id?: string
          install_status?: Database["public"]["Enums"]["capability_status"]
          kind: Database["public"]["Enums"]["capability_kind"]
          org_id: string
          plugin_id?: string | null
          plugin_version?: string | null
          updated_at?: string
        }
        Update: {
          args?: Json
          created_at?: string
          daemon_id?: string
          endpoint?: string | null
          exposed_tools?: string[]
          id?: string
          install_status?: Database["public"]["Enums"]["capability_status"]
          kind?: Database["public"]["Enums"]["capability_kind"]
          org_id?: string
          plugin_id?: string | null
          plugin_version?: string | null
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "daemon_capabilities_daemon_id_fkey"
            columns: ["daemon_id"]
            isOneToOne: false
            referencedRelation: "daemon_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "daemon_capabilities_daemon_id_fkey"
            columns: ["daemon_id"]
            isOneToOne: false
            referencedRelation: "daemons"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "daemon_capabilities_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "daemon_capabilities_plugin_id_fkey"
            columns: ["plugin_id"]
            isOneToOne: false
            referencedRelation: "plugins"
            referencedColumns: ["id"]
          },
        ]
      }
      daemon_presence: {
        Row: {
          daemon_id: string
          expires_at: string
          hub_node: string | null
          last_heartbeat: string
          org_id: string
        }
        Insert: {
          daemon_id: string
          expires_at: string
          hub_node?: string | null
          last_heartbeat?: string
          org_id: string
        }
        Update: {
          daemon_id?: string
          expires_at?: string
          hub_node?: string | null
          last_heartbeat?: string
          org_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "daemon_presence_daemon_id_fkey"
            columns: ["daemon_id"]
            isOneToOne: true
            referencedRelation: "daemon_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "daemon_presence_daemon_id_fkey"
            columns: ["daemon_id"]
            isOneToOne: true
            referencedRelation: "daemons"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "daemon_presence_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
        ]
      }
      daemons: {
        Row: {
          created_at: string
          e2e_public_key: string | null
          hostname: string | null
          id: string
          last_ip: unknown
          last_seen: string | null
          name: string
          org_id: string
          os_version: string | null
          platform: string | null
          refresh_token_hash: string | null
          refresh_token_issued_at: string | null
          revoked_at: string | null
          status: Database["public"]["Enums"]["daemon_status"]
          tags: string[]
          version: string | null
        }
        Insert: {
          created_at?: string
          e2e_public_key?: string | null
          hostname?: string | null
          id?: string
          last_ip?: unknown
          last_seen?: string | null
          name: string
          org_id: string
          os_version?: string | null
          platform?: string | null
          refresh_token_hash?: string | null
          refresh_token_issued_at?: string | null
          revoked_at?: string | null
          status?: Database["public"]["Enums"]["daemon_status"]
          tags?: string[]
          version?: string | null
        }
        Update: {
          created_at?: string
          e2e_public_key?: string | null
          hostname?: string | null
          id?: string
          last_ip?: unknown
          last_seen?: string | null
          name?: string
          org_id?: string
          os_version?: string | null
          platform?: string | null
          refresh_token_hash?: string | null
          refresh_token_issued_at?: string | null
          revoked_at?: string | null
          status?: Database["public"]["Enums"]["daemon_status"]
          tags?: string[]
          version?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "daemons_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
        ]
      }
      device_authorizations: {
        Row: {
          created_at: string
          daemon_id: string | null
          daemon_version: string | null
          device_code_hash: string
          expires_at: string
          hostname: string | null
          id: string
          interval_seconds: number
          org_id: string | null
          os_version: string | null
          request_ip: unknown
          status: Database["public"]["Enums"]["device_auth_status"]
          user_code: string
          user_id: string | null
        }
        Insert: {
          created_at?: string
          daemon_id?: string | null
          daemon_version?: string | null
          device_code_hash: string
          expires_at: string
          hostname?: string | null
          id?: string
          interval_seconds?: number
          org_id?: string | null
          os_version?: string | null
          request_ip?: unknown
          status?: Database["public"]["Enums"]["device_auth_status"]
          user_code: string
          user_id?: string | null
        }
        Update: {
          created_at?: string
          daemon_id?: string | null
          daemon_version?: string | null
          device_code_hash?: string
          expires_at?: string
          hostname?: string | null
          id?: string
          interval_seconds?: number
          org_id?: string | null
          os_version?: string | null
          request_ip?: unknown
          status?: Database["public"]["Enums"]["device_auth_status"]
          user_code?: string
          user_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "device_authorizations_daemon_id_fkey"
            columns: ["daemon_id"]
            isOneToOne: false
            referencedRelation: "daemon_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "device_authorizations_daemon_id_fkey"
            columns: ["daemon_id"]
            isOneToOne: false
            referencedRelation: "daemons"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "device_authorizations_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "device_authorizations_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
        ]
      }
      env_var_refs: {
        Row: {
          agent_id: string | null
          daemon_id: string | null
          id: string
          name: string
          org_id: string
          origin: Database["public"]["Enums"]["env_var_origin"]
          scope: Database["public"]["Enums"]["env_var_scope"]
          secret: boolean
          updated_at: string
          updated_by: string | null
          value_plain: string | null
        }
        Insert: {
          agent_id?: string | null
          daemon_id?: string | null
          id?: string
          name: string
          org_id: string
          origin?: Database["public"]["Enums"]["env_var_origin"]
          scope?: Database["public"]["Enums"]["env_var_scope"]
          secret?: boolean
          updated_at?: string
          updated_by?: string | null
          value_plain?: string | null
        }
        Update: {
          agent_id?: string | null
          daemon_id?: string | null
          id?: string
          name?: string
          org_id?: string
          origin?: Database["public"]["Enums"]["env_var_origin"]
          scope?: Database["public"]["Enums"]["env_var_scope"]
          secret?: boolean
          updated_at?: string
          updated_by?: string | null
          value_plain?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "env_var_refs_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: false
            referencedRelation: "agent_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "env_var_refs_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: false
            referencedRelation: "agents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "env_var_refs_daemon_id_fkey"
            columns: ["daemon_id"]
            isOneToOne: false
            referencedRelation: "daemon_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "env_var_refs_daemon_id_fkey"
            columns: ["daemon_id"]
            isOneToOne: false
            referencedRelation: "daemons"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "env_var_refs_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
        ]
      }
      gateways: {
        Row: {
          agent_id: string | null
          config: Json
          created_at: string
          id: string
          kind: string
          name: string
          org_id: string
        }
        Insert: {
          agent_id?: string | null
          config?: Json
          created_at?: string
          id?: string
          kind: string
          name: string
          org_id: string
        }
        Update: {
          agent_id?: string | null
          config?: Json
          created_at?: string
          id?: string
          kind?: string
          name?: string
          org_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "gateways_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: false
            referencedRelation: "agent_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "gateways_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: false
            referencedRelation: "agents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "gateways_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
        ]
      }
      hitl_requests: {
        Row: {
          action: string
          agent_id: string | null
          context: Json | null
          created_at: string
          daemon_id: string | null
          expires_at: string | null
          id: string
          org_id: string
          resolution_reason: string | null
          resolved_at: string | null
          resolved_by: string | null
          run_id: string | null
          severity: Database["public"]["Enums"]["hitl_severity"]
          simulated: boolean
          status: Database["public"]["Enums"]["hitl_status"]
        }
        Insert: {
          action: string
          agent_id?: string | null
          context?: Json | null
          created_at?: string
          daemon_id?: string | null
          expires_at?: string | null
          id?: string
          org_id: string
          resolution_reason?: string | null
          resolved_at?: string | null
          resolved_by?: string | null
          run_id?: string | null
          severity?: Database["public"]["Enums"]["hitl_severity"]
          simulated?: boolean
          status?: Database["public"]["Enums"]["hitl_status"]
        }
        Update: {
          action?: string
          agent_id?: string | null
          context?: Json | null
          created_at?: string
          daemon_id?: string | null
          expires_at?: string | null
          id?: string
          org_id?: string
          resolution_reason?: string | null
          resolved_at?: string | null
          resolved_by?: string | null
          run_id?: string | null
          severity?: Database["public"]["Enums"]["hitl_severity"]
          simulated?: boolean
          status?: Database["public"]["Enums"]["hitl_status"]
        }
        Relationships: [
          {
            foreignKeyName: "hitl_requests_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: false
            referencedRelation: "agent_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "hitl_requests_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: false
            referencedRelation: "agents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "hitl_requests_daemon_id_fkey"
            columns: ["daemon_id"]
            isOneToOne: false
            referencedRelation: "daemon_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "hitl_requests_daemon_id_fkey"
            columns: ["daemon_id"]
            isOneToOne: false
            referencedRelation: "daemons"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "hitl_requests_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "hitl_requests_resolved_by_fkey"
            columns: ["resolved_by"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "hitl_requests_run_id_fkey"
            columns: ["run_id"]
            isOneToOne: false
            referencedRelation: "runs"
            referencedColumns: ["id"]
          },
        ]
      }
      job_leases: {
        Row: {
          job: string
          locked_until: string
          updated_at: string
        }
        Insert: {
          job: string
          locked_until?: string
          updated_at?: string
        }
        Update: {
          job?: string
          locked_until?: string
          updated_at?: string
        }
        Relationships: []
      }
      logs: {
        Row: {
          agent_id: string | null
          created_at: string
          daemon_id: string | null
          fields: Json
          id: string
          level: string | null
          message: string | null
          org_id: string
          run_id: string | null
        }
        Insert: {
          agent_id?: string | null
          created_at?: string
          daemon_id?: string | null
          fields?: Json
          id?: string
          level?: string | null
          message?: string | null
          org_id: string
          run_id?: string | null
        }
        Update: {
          agent_id?: string | null
          created_at?: string
          daemon_id?: string | null
          fields?: Json
          id?: string
          level?: string | null
          message?: string | null
          org_id?: string
          run_id?: string | null
        }
        Relationships: []
      }
      logs_default: {
        Row: {
          agent_id: string | null
          created_at: string
          daemon_id: string | null
          fields: Json
          id: string
          level: string | null
          message: string | null
          org_id: string
          run_id: string | null
        }
        Insert: {
          agent_id?: string | null
          created_at?: string
          daemon_id?: string | null
          fields?: Json
          id?: string
          level?: string | null
          message?: string | null
          org_id: string
          run_id?: string | null
        }
        Update: {
          agent_id?: string | null
          created_at?: string
          daemon_id?: string | null
          fields?: Json
          id?: string
          level?: string | null
          message?: string | null
          org_id?: string
          run_id?: string | null
        }
        Relationships: []
      }
      marketplace_installs: {
        Row: {
          agent_id: string | null
          created_at: string
          daemon_id: string | null
          id: string
          installed_by: string | null
          listing_id: string
          org_id: string
        }
        Insert: {
          agent_id?: string | null
          created_at?: string
          daemon_id?: string | null
          id?: string
          installed_by?: string | null
          listing_id: string
          org_id: string
        }
        Update: {
          agent_id?: string | null
          created_at?: string
          daemon_id?: string | null
          id?: string
          installed_by?: string | null
          listing_id?: string
          org_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "marketplace_installs_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: false
            referencedRelation: "agent_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "marketplace_installs_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: false
            referencedRelation: "agents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "marketplace_installs_daemon_id_fkey"
            columns: ["daemon_id"]
            isOneToOne: false
            referencedRelation: "daemon_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "marketplace_installs_daemon_id_fkey"
            columns: ["daemon_id"]
            isOneToOne: false
            referencedRelation: "daemons"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "marketplace_installs_installed_by_fkey"
            columns: ["installed_by"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "marketplace_installs_listing_id_fkey"
            columns: ["listing_id"]
            isOneToOne: false
            referencedRelation: "marketplace_listings"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "marketplace_installs_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
        ]
      }
      marketplace_listings: {
        Row: {
          checksum: string | null
          created_at: string
          description: string | null
          id: string
          kind: Database["public"]["Enums"]["listing_kind"]
          manifest_ref: string | null
          name: string
          permissions: Json
          platforms: string[]
          ratings: Json
          required_tools: Json
          signature: string | null
          version: string | null
        }
        Insert: {
          checksum?: string | null
          created_at?: string
          description?: string | null
          id?: string
          kind: Database["public"]["Enums"]["listing_kind"]
          manifest_ref?: string | null
          name: string
          permissions?: Json
          platforms?: string[]
          ratings?: Json
          required_tools?: Json
          signature?: string | null
          version?: string | null
        }
        Update: {
          checksum?: string | null
          created_at?: string
          description?: string | null
          id?: string
          kind?: Database["public"]["Enums"]["listing_kind"]
          manifest_ref?: string | null
          name?: string
          permissions?: Json
          platforms?: string[]
          ratings?: Json
          required_tools?: Json
          signature?: string | null
          version?: string | null
        }
        Relationships: []
      }
      memberships: {
        Row: {
          created_at: string
          id: string
          org_id: string
          role: Database["public"]["Enums"]["membership_role"]
          user_id: string
        }
        Insert: {
          created_at?: string
          id?: string
          org_id: string
          role?: Database["public"]["Enums"]["membership_role"]
          user_id: string
        }
        Update: {
          created_at?: string
          id?: string
          org_id?: string
          role?: Database["public"]["Enums"]["membership_role"]
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "memberships_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "memberships_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
        ]
      }
      metric_rollups: {
        Row: {
          agent_id: string | null
          avg: number | null
          bucket: string
          bucket_start: string
          count: number
          created_at: string
          daemon_id: string | null
          ewma: number | null
          id: string
          max: number | null
          metric: string
          min: number | null
          org_id: string
          p95: number | null
          sum: number
        }
        Insert: {
          agent_id?: string | null
          avg?: number | null
          bucket: string
          bucket_start: string
          count?: number
          created_at?: string
          daemon_id?: string | null
          ewma?: number | null
          id?: string
          max?: number | null
          metric: string
          min?: number | null
          org_id: string
          p95?: number | null
          sum?: number
        }
        Update: {
          agent_id?: string | null
          avg?: number | null
          bucket?: string
          bucket_start?: string
          count?: number
          created_at?: string
          daemon_id?: string | null
          ewma?: number | null
          id?: string
          max?: number | null
          metric?: string
          min?: number | null
          org_id?: string
          p95?: number | null
          sum?: number
        }
        Relationships: [
          {
            foreignKeyName: "metric_rollups_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: false
            referencedRelation: "agent_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "metric_rollups_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: false
            referencedRelation: "agents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "metric_rollups_daemon_id_fkey"
            columns: ["daemon_id"]
            isOneToOne: false
            referencedRelation: "daemon_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "metric_rollups_daemon_id_fkey"
            columns: ["daemon_id"]
            isOneToOne: false
            referencedRelation: "daemons"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "metric_rollups_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
        ]
      }
      metrics: {
        Row: {
          agent_id: string | null
          created_at: string
          daemon_id: string | null
          id: string
          labels: Json
          name: string
          org_id: string
          run_id: string | null
          value: number
        }
        Insert: {
          agent_id?: string | null
          created_at?: string
          daemon_id?: string | null
          id?: string
          labels?: Json
          name: string
          org_id: string
          run_id?: string | null
          value: number
        }
        Update: {
          agent_id?: string | null
          created_at?: string
          daemon_id?: string | null
          id?: string
          labels?: Json
          name?: string
          org_id?: string
          run_id?: string | null
          value?: number
        }
        Relationships: []
      }
      metrics_default: {
        Row: {
          agent_id: string | null
          created_at: string
          daemon_id: string | null
          id: string
          labels: Json
          name: string
          org_id: string
          run_id: string | null
          value: number
        }
        Insert: {
          agent_id?: string | null
          created_at?: string
          daemon_id?: string | null
          id?: string
          labels?: Json
          name: string
          org_id: string
          run_id?: string | null
          value: number
        }
        Update: {
          agent_id?: string | null
          created_at?: string
          daemon_id?: string | null
          id?: string
          labels?: Json
          name?: string
          org_id?: string
          run_id?: string | null
          value?: number
        }
        Relationships: []
      }
      notification_channels: {
        Row: {
          config: Json
          created_at: string
          enabled: boolean
          id: string
          kind: Database["public"]["Enums"]["notification_channel_kind"]
          org_id: string
          routing_rules: Json
        }
        Insert: {
          config?: Json
          created_at?: string
          enabled?: boolean
          id?: string
          kind: Database["public"]["Enums"]["notification_channel_kind"]
          org_id: string
          routing_rules?: Json
        }
        Update: {
          config?: Json
          created_at?: string
          enabled?: boolean
          id?: string
          kind?: Database["public"]["Enums"]["notification_channel_kind"]
          org_id?: string
          routing_rules?: Json
        }
        Relationships: [
          {
            foreignKeyName: "notification_channels_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
        ]
      }
      org_invitations: {
        Row: {
          accepted_at: string | null
          created_at: string
          email: string
          id: string
          invited_by: string | null
          org_id: string
          role: Database["public"]["Enums"]["membership_role"]
          status: Database["public"]["Enums"]["invitation_status"]
          token: string
        }
        Insert: {
          accepted_at?: string | null
          created_at?: string
          email: string
          id?: string
          invited_by?: string | null
          org_id: string
          role?: Database["public"]["Enums"]["membership_role"]
          status?: Database["public"]["Enums"]["invitation_status"]
          token?: string
        }
        Update: {
          accepted_at?: string | null
          created_at?: string
          email?: string
          id?: string
          invited_by?: string | null
          org_id?: string
          role?: Database["public"]["Enums"]["membership_role"]
          status?: Database["public"]["Enums"]["invitation_status"]
          token?: string
        }
        Relationships: [
          {
            foreignKeyName: "org_invitations_invited_by_fkey"
            columns: ["invited_by"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "org_invitations_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
        ]
      }
      org_security_policy: {
        Row: {
          created_at: string
          mfa_grace_until: string | null
          org_id: string
          require_mfa: boolean
          step_up_max_age: number
          updated_at: string
        }
        Insert: {
          created_at?: string
          mfa_grace_until?: string | null
          org_id: string
          require_mfa?: boolean
          step_up_max_age?: number
          updated_at?: string
        }
        Update: {
          created_at?: string
          mfa_grace_until?: string | null
          org_id?: string
          require_mfa?: boolean
          step_up_max_age?: number
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "org_security_policy_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: true
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
        ]
      }
      organizations: {
        Row: {
          created_at: string
          id: string
          name: string
          recovery_public_key: string | null
          settings: Json
        }
        Insert: {
          created_at?: string
          id?: string
          name: string
          recovery_public_key?: string | null
          settings?: Json
        }
        Update: {
          created_at?: string
          id?: string
          name?: string
          recovery_public_key?: string | null
          settings?: Json
        }
        Relationships: []
      }
      plugins: {
        Row: {
          checksum: string | null
          created_at: string
          declared_permissions: Json
          id: string
          kind: Database["public"]["Enums"]["capability_kind"]
          manifest_ref: string | null
          name: string
          platforms: string[]
          ratings: Json
          signature: string | null
          versions: Json
        }
        Insert: {
          checksum?: string | null
          created_at?: string
          declared_permissions?: Json
          id?: string
          kind: Database["public"]["Enums"]["capability_kind"]
          manifest_ref?: string | null
          name: string
          platforms?: string[]
          ratings?: Json
          signature?: string | null
          versions?: Json
        }
        Update: {
          checksum?: string | null
          created_at?: string
          declared_permissions?: Json
          id?: string
          kind?: Database["public"]["Enums"]["capability_kind"]
          manifest_ref?: string | null
          name?: string
          platforms?: string[]
          ratings?: Json
          signature?: string | null
          versions?: Json
        }
        Relationships: []
      }
      reasoning_traces: {
        Row: {
          agent_id: string | null
          blob_ref: string | null
          content_redacted: string | null
          created_at: string
          id: string
          org_id: string
          role: string | null
          run_id: string | null
          seq: number | null
        }
        Insert: {
          agent_id?: string | null
          blob_ref?: string | null
          content_redacted?: string | null
          created_at?: string
          id?: string
          org_id: string
          role?: string | null
          run_id?: string | null
          seq?: number | null
        }
        Update: {
          agent_id?: string | null
          blob_ref?: string | null
          content_redacted?: string | null
          created_at?: string
          id?: string
          org_id?: string
          role?: string | null
          run_id?: string | null
          seq?: number | null
        }
        Relationships: []
      }
      reasoning_traces_default: {
        Row: {
          agent_id: string | null
          blob_ref: string | null
          content_redacted: string | null
          created_at: string
          id: string
          org_id: string
          role: string | null
          run_id: string | null
          seq: number | null
        }
        Insert: {
          agent_id?: string | null
          blob_ref?: string | null
          content_redacted?: string | null
          created_at?: string
          id?: string
          org_id: string
          role?: string | null
          run_id?: string | null
          seq?: number | null
        }
        Update: {
          agent_id?: string | null
          blob_ref?: string | null
          content_redacted?: string | null
          created_at?: string
          id?: string
          org_id?: string
          role?: string | null
          run_id?: string | null
          seq?: number | null
        }
        Relationships: []
      }
      recovery_codes: {
        Row: {
          code_hash: string
          created_at: string
          id: string
          used_at: string | null
          user_id: string
        }
        Insert: {
          code_hash: string
          created_at?: string
          id?: string
          used_at?: string | null
          user_id: string
        }
        Update: {
          code_hash?: string
          created_at?: string
          id?: string
          used_at?: string | null
          user_id?: string
        }
        Relationships: []
      }
      run_checkpoints: {
        Row: {
          cost_so_far_usd: number
          created_at: string
          daemon_id: string | null
          id: string
          org_id: string
          payload_blob_ref: string | null
          run_id: string
          seq: number
          status: Database["public"]["Enums"]["run_status"] | null
          step_cursor: number | null
        }
        Insert: {
          cost_so_far_usd?: number
          created_at?: string
          daemon_id?: string | null
          id?: string
          org_id: string
          payload_blob_ref?: string | null
          run_id: string
          seq: number
          status?: Database["public"]["Enums"]["run_status"] | null
          step_cursor?: number | null
        }
        Update: {
          cost_so_far_usd?: number
          created_at?: string
          daemon_id?: string | null
          id?: string
          org_id?: string
          payload_blob_ref?: string | null
          run_id?: string
          seq?: number
          status?: Database["public"]["Enums"]["run_status"] | null
          step_cursor?: number | null
        }
        Relationships: [
          {
            foreignKeyName: "run_checkpoints_daemon_id_fkey"
            columns: ["daemon_id"]
            isOneToOne: false
            referencedRelation: "daemon_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "run_checkpoints_daemon_id_fkey"
            columns: ["daemon_id"]
            isOneToOne: false
            referencedRelation: "daemons"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "run_checkpoints_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "run_checkpoints_run_id_fkey"
            columns: ["run_id"]
            isOneToOne: false
            referencedRelation: "runs"
            referencedColumns: ["id"]
          },
        ]
      }
      run_groups: {
        Row: {
          agent_id: string
          agent_version: number | null
          created_at: string
          created_by: string | null
          daemon_id: string | null
          group_cost_cap: number | null
          id: string
          input: Json
          max_parallel_variants: number
          org_id: string
          selected_models: string[]
          status: string
          total_cost_usd: number
          updated_at: string
          winner_run_id: string | null
        }
        Insert: {
          agent_id: string
          agent_version?: number | null
          created_at?: string
          created_by?: string | null
          daemon_id?: string | null
          group_cost_cap?: number | null
          id?: string
          input?: Json
          max_parallel_variants?: number
          org_id: string
          selected_models?: string[]
          status?: string
          total_cost_usd?: number
          updated_at?: string
          winner_run_id?: string | null
        }
        Update: {
          agent_id?: string
          agent_version?: number | null
          created_at?: string
          created_by?: string | null
          daemon_id?: string | null
          group_cost_cap?: number | null
          id?: string
          input?: Json
          max_parallel_variants?: number
          org_id?: string
          selected_models?: string[]
          status?: string
          total_cost_usd?: number
          updated_at?: string
          winner_run_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "run_groups_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: false
            referencedRelation: "agent_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "run_groups_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: false
            referencedRelation: "agents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "run_groups_created_by_fkey"
            columns: ["created_by"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "run_groups_daemon_id_fkey"
            columns: ["daemon_id"]
            isOneToOne: false
            referencedRelation: "daemon_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "run_groups_daemon_id_fkey"
            columns: ["daemon_id"]
            isOneToOne: false
            referencedRelation: "daemons"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "run_groups_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "run_groups_winner_run_id_fkey"
            columns: ["winner_run_id"]
            isOneToOne: false
            referencedRelation: "runs"
            referencedColumns: ["id"]
          },
        ]
      }
      runs: {
        Row: {
          agent_id: string
          agent_version: number | null
          cost_usd: number
          created_at: string
          daemon_id: string | null
          depth: number
          ended_at: string | null
          exit_code: number | null
          flow_id: string | null
          handoff_mode: string | null
          hop: number
          id: string
          idempotency_key: string | null
          initiator: string
          initiator_agent_id: string | null
          is_winner: boolean
          mode: string
          org_id: string
          parent_run_id: string | null
          redaction_summary: Json | null
          root_run_id: string | null
          run_group_id: string | null
          started_at: string | null
          status: Database["public"]["Enums"]["run_status"]
          tokens_in: number
          tokens_out: number
          trigger: Database["public"]["Enums"]["trigger_source"]
          variant_model: string | null
        }
        Insert: {
          agent_id: string
          agent_version?: number | null
          cost_usd?: number
          created_at?: string
          daemon_id?: string | null
          depth?: number
          ended_at?: string | null
          exit_code?: number | null
          flow_id?: string | null
          handoff_mode?: string | null
          hop?: number
          id?: string
          idempotency_key?: string | null
          initiator?: string
          initiator_agent_id?: string | null
          is_winner?: boolean
          mode?: string
          org_id: string
          parent_run_id?: string | null
          redaction_summary?: Json | null
          root_run_id?: string | null
          run_group_id?: string | null
          started_at?: string | null
          status?: Database["public"]["Enums"]["run_status"]
          tokens_in?: number
          tokens_out?: number
          trigger?: Database["public"]["Enums"]["trigger_source"]
          variant_model?: string | null
        }
        Update: {
          agent_id?: string
          agent_version?: number | null
          cost_usd?: number
          created_at?: string
          daemon_id?: string | null
          depth?: number
          ended_at?: string | null
          exit_code?: number | null
          flow_id?: string | null
          handoff_mode?: string | null
          hop?: number
          id?: string
          idempotency_key?: string | null
          initiator?: string
          initiator_agent_id?: string | null
          is_winner?: boolean
          mode?: string
          org_id?: string
          parent_run_id?: string | null
          redaction_summary?: Json | null
          root_run_id?: string | null
          run_group_id?: string | null
          started_at?: string | null
          status?: Database["public"]["Enums"]["run_status"]
          tokens_in?: number
          tokens_out?: number
          trigger?: Database["public"]["Enums"]["trigger_source"]
          variant_model?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "runs_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: false
            referencedRelation: "agent_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "runs_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: false
            referencedRelation: "agents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "runs_daemon_id_fkey"
            columns: ["daemon_id"]
            isOneToOne: false
            referencedRelation: "daemon_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "runs_daemon_id_fkey"
            columns: ["daemon_id"]
            isOneToOne: false
            referencedRelation: "daemons"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "runs_flow_id_fkey"
            columns: ["flow_id"]
            isOneToOne: false
            referencedRelation: "agent_flows"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "runs_initiator_agent_id_fkey"
            columns: ["initiator_agent_id"]
            isOneToOne: false
            referencedRelation: "agent_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "runs_initiator_agent_id_fkey"
            columns: ["initiator_agent_id"]
            isOneToOne: false
            referencedRelation: "agents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "runs_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "runs_run_group_id_fkey"
            columns: ["run_group_id"]
            isOneToOne: false
            referencedRelation: "run_groups"
            referencedColumns: ["id"]
          },
        ]
      }
      schedules: {
        Row: {
          agent_id: string
          created_at: string
          cron_expr: string | null
          enabled: boolean
          id: string
          interval_seconds: number | null
          kind: Database["public"]["Enums"]["schedule_kind"]
          org_id: string
          run_at: string | null
          schedule_auth: Json | null
        }
        Insert: {
          agent_id: string
          created_at?: string
          cron_expr?: string | null
          enabled?: boolean
          id?: string
          interval_seconds?: number | null
          kind: Database["public"]["Enums"]["schedule_kind"]
          org_id: string
          run_at?: string | null
          schedule_auth?: Json | null
        }
        Update: {
          agent_id?: string
          created_at?: string
          cron_expr?: string | null
          enabled?: boolean
          id?: string
          interval_seconds?: number | null
          kind?: Database["public"]["Enums"]["schedule_kind"]
          org_id?: string
          run_at?: string | null
          schedule_auth?: Json | null
        }
        Relationships: [
          {
            foreignKeyName: "schedules_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: false
            referencedRelation: "agent_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "schedules_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: false
            referencedRelation: "agents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "schedules_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
        ]
      }
      team_memberships: {
        Row: {
          created_at: string
          id: string
          org_id: string
          team_id: string
          user_id: string
        }
        Insert: {
          created_at?: string
          id?: string
          org_id: string
          team_id: string
          user_id: string
        }
        Update: {
          created_at?: string
          id?: string
          org_id?: string
          team_id?: string
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "team_memberships_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "team_memberships_team_id_fkey"
            columns: ["team_id"]
            isOneToOne: false
            referencedRelation: "teams"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "team_memberships_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
        ]
      }
      teams: {
        Row: {
          created_at: string
          id: string
          name: string
          org_id: string
          parent_team_id: string | null
        }
        Insert: {
          created_at?: string
          id?: string
          name: string
          org_id: string
          parent_team_id?: string | null
        }
        Update: {
          created_at?: string
          id?: string
          name?: string
          org_id?: string
          parent_team_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "teams_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "teams_parent_team_id_fkey"
            columns: ["parent_team_id"]
            isOneToOne: false
            referencedRelation: "teams"
            referencedColumns: ["id"]
          },
        ]
      }
      tool_calls: {
        Row: {
          args_redacted: Json | null
          cost_usd: number
          created_at: string
          id: string
          latency_ms: number | null
          name: string
          org_id: string
          proposed_action: boolean
          result_redacted: Json | null
          run_id: string
          simulated: boolean
        }
        Insert: {
          args_redacted?: Json | null
          cost_usd?: number
          created_at?: string
          id?: string
          latency_ms?: number | null
          name: string
          org_id: string
          proposed_action?: boolean
          result_redacted?: Json | null
          run_id: string
          simulated?: boolean
        }
        Update: {
          args_redacted?: Json | null
          cost_usd?: number
          created_at?: string
          id?: string
          latency_ms?: number | null
          name?: string
          org_id?: string
          proposed_action?: boolean
          result_redacted?: Json | null
          run_id?: string
          simulated?: boolean
        }
        Relationships: [
          {
            foreignKeyName: "tool_calls_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "tool_calls_run_id_fkey"
            columns: ["run_id"]
            isOneToOne: false
            referencedRelation: "runs"
            referencedColumns: ["id"]
          },
        ]
      }
      users: {
        Row: {
          command_public_key: string | null
          created_at: string
          display_name: string | null
          email: string | null
          id: string
          mfa_enrolled: boolean
        }
        Insert: {
          command_public_key?: string | null
          created_at?: string
          display_name?: string | null
          email?: string | null
          id: string
          mfa_enrolled?: boolean
        }
        Update: {
          command_public_key?: string | null
          created_at?: string
          display_name?: string | null
          email?: string | null
          id?: string
          mfa_enrolled?: boolean
        }
        Relationships: []
      }
      webhooks: {
        Row: {
          agent_id: string
          created_at: string
          enabled: boolean
          id: string
          org_id: string
          payload_template: Json | null
          secret_hash: string | null
          token: string
        }
        Insert: {
          agent_id: string
          created_at?: string
          enabled?: boolean
          id?: string
          org_id: string
          payload_template?: Json | null
          secret_hash?: string | null
          token: string
        }
        Update: {
          agent_id?: string
          created_at?: string
          enabled?: boolean
          id?: string
          org_id?: string
          payload_template?: Json | null
          secret_hash?: string | null
          token?: string
        }
        Relationships: [
          {
            foreignKeyName: "webhooks_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: false
            referencedRelation: "agent_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "webhooks_agent_id_fkey"
            columns: ["agent_id"]
            isOneToOne: false
            referencedRelation: "agents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "webhooks_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
        ]
      }
    }
    Views: {
      agent_overview: {
        Row: {
          current_version: number | null
          daemon_id: string | null
          description: string | null
          engine: string | null
          err_rate: number | null
          has_webhook: boolean | null
          id: string | null
          last_run_at: string | null
          model: string | null
          name: string | null
          next_run_at: string | null
          org_id: string | null
          prompt: string | null
          runs_total: number | null
          spend_today: number | null
          status: Database["public"]["Enums"]["agent_status"] | null
          tokens_today: number | null
          type: Database["public"]["Enums"]["agent_type"] | null
          updated_at: string | null
        }
        Relationships: [
          {
            foreignKeyName: "agents_daemon_id_fkey"
            columns: ["daemon_id"]
            isOneToOne: false
            referencedRelation: "daemon_overview"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agents_daemon_id_fkey"
            columns: ["daemon_id"]
            isOneToOne: false
            referencedRelation: "daemons"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agents_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
        ]
      }
      daemon_overview: {
        Row: {
          active_runs: number | null
          cpu: number | null
          expires_at: string | null
          hostname: string | null
          id: string | null
          last_heartbeat: string | null
          last_ip: unknown
          last_seen: string | null
          mem: number | null
          name: string | null
          org_id: string | null
          os_version: string | null
          platform: string | null
          status: Database["public"]["Enums"]["daemon_status"] | null
          tags: string[] | null
          version: string | null
        }
        Relationships: [
          {
            foreignKeyName: "daemons_org_id_fkey"
            columns: ["org_id"]
            isOneToOne: false
            referencedRelation: "organizations"
            referencedColumns: ["id"]
          },
        ]
      }
    }
    Functions: {
      user_has_role: {
        Args: {
          roles: Database["public"]["Enums"]["membership_role"][]
          target_org: string
        }
        Returns: boolean
      }
      user_org_ids: { Args: never; Returns: string[] }
    }
    Enums: {
      agent_status: "active" | "paused" | "archived"
      agent_type: "api" | "cli"
      anomaly_severity: "info" | "warning" | "critical"
      capability_kind: "mcp" | "script" | "workspace" | "composite"
      capability_status: "installing" | "ready" | "failed"
      daemon_status: "online" | "offline" | "revoked"
      device_auth_status: "pending" | "authorized" | "denied" | "expired"
      env_var_origin: "ui" | "local"
      env_var_scope: "agent" | "shared"
      hitl_severity: "block" | "require-approval"
      hitl_status: "pending" | "approved" | "denied" | "expired"
      invitation_status: "pending" | "accepted" | "revoked"
      listing_kind: "agent" | "skill" | "plugin"
      membership_role: "owner" | "admin" | "operator" | "viewer"
      notification_channel_kind: "slack" | "discord" | "email" | "in_app"
      run_status:
        | "pending"
        | "running"
        | "succeeded"
        | "failed"
        | "cancelled"
        | "interrupted"
        | "recovering"
        | "resumed"
      schedule_kind: "cron" | "interval" | "one_shot"
      trigger_source: "manual" | "schedule" | "webhook" | "recovery"
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  public: {
    Enums: {
      agent_status: ["active", "paused", "archived"],
      agent_type: ["api", "cli"],
      anomaly_severity: ["info", "warning", "critical"],
      capability_kind: ["mcp", "script", "workspace", "composite"],
      capability_status: ["installing", "ready", "failed"],
      daemon_status: ["online", "offline", "revoked"],
      device_auth_status: ["pending", "authorized", "denied", "expired"],
      env_var_origin: ["ui", "local"],
      env_var_scope: ["agent", "shared"],
      hitl_severity: ["block", "require-approval"],
      hitl_status: ["pending", "approved", "denied", "expired"],
      invitation_status: ["pending", "accepted", "revoked"],
      listing_kind: ["agent", "skill", "plugin"],
      membership_role: ["owner", "admin", "operator", "viewer"],
      notification_channel_kind: ["slack", "discord", "email", "in_app"],
      run_status: [
        "pending",
        "running",
        "succeeded",
        "failed",
        "cancelled",
        "interrupted",
        "recovering",
        "resumed",
      ],
      schedule_kind: ["cron", "interval", "one_shot"],
      trigger_source: ["manual", "schedule", "webhook", "recovery"],
    },
  },
} as const
