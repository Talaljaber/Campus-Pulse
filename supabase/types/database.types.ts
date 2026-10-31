// GENERATED — do not edit. Supabase MCP generate_typescript_types for project efsanbaklpiakhsndhph
// after migration 0008. Regenerate after every migration: see docs/db/schema.md › TypeScript types.
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
    PostgrestVersion: "14.18"
  }
  public: {
    Tables: {
      advisor_slots: {
        Row: {
          advisor_id: string
          booked_at: string | null
          booked_by: string | null
          created_at: string
          ends_at: string
          id: string
          starts_at: string
        }
        Insert: {
          advisor_id: string
          booked_at?: string | null
          booked_by?: string | null
          created_at?: string
          ends_at: string
          id?: string
          starts_at: string
        }
        Update: {
          advisor_id?: string
          booked_at?: string | null
          booked_by?: string | null
          created_at?: string
          ends_at?: string
          id?: string
          starts_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "advisor_slots_advisor_id_fkey"
            columns: ["advisor_id"]
            isOneToOne: false
            referencedRelation: "advisors"
            referencedColumns: ["id"]
          },
        ]
      }
      advisors: {
        Row: {
          calendar_id: string | null
          created_at: string
          demo_email: string | null
          department: string
          fictional_name: string
          id: string
          office_hours: Json | null
          room: string | null
        }
        Insert: {
          calendar_id?: string | null
          created_at?: string
          demo_email?: string | null
          department: string
          fictional_name: string
          id?: string
          office_hours?: Json | null
          room?: string | null
        }
        Update: {
          calendar_id?: string | null
          created_at?: string
          demo_email?: string | null
          department?: string
          fictional_name?: string
          id?: string
          office_hours?: Json | null
          room?: string | null
        }
        Relationships: []
      }
      buildings: {
        Row: {
          code: string
          id: string
          map_x: number | null
          map_y: number | null
          name_ar: string
          name_en: string
        }
        Insert: {
          code: string
          id: string
          map_x?: number | null
          map_y?: number | null
          name_ar: string
          name_en: string
        }
        Update: {
          code?: string
          id?: string
          map_x?: number | null
          map_y?: number | null
          name_ar?: string
          name_en?: string
        }
        Relationships: []
      }
      cases: {
        Row: {
          advisor_id: string | null
          booking: Json | null
          closed_at: string | null
          created_at: string
          id: string
          outcome_code: string | null
          request_id: string | null
          slot_id: string | null
          slot_start: string | null
          ticket_id: string | null
        }
        Insert: {
          advisor_id?: string | null
          booking?: Json | null
          closed_at?: string | null
          created_at?: string
          id?: string
          outcome_code?: string | null
          request_id?: string | null
          slot_id?: string | null
          slot_start?: string | null
          ticket_id?: string | null
        }
        Update: {
          advisor_id?: string | null
          booking?: Json | null
          closed_at?: string | null
          created_at?: string
          id?: string
          outcome_code?: string | null
          request_id?: string | null
          slot_id?: string | null
          slot_start?: string | null
          ticket_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "cases_advisor_id_fkey"
            columns: ["advisor_id"]
            isOneToOne: false
            referencedRelation: "advisors"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "cases_request_id_fkey"
            columns: ["request_id"]
            isOneToOne: false
            referencedRelation: "requests"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "cases_slot_id_fkey"
            columns: ["slot_id"]
            isOneToOne: false
            referencedRelation: "advisor_slots"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "cases_ticket_id_fkey"
            columns: ["ticket_id"]
            isOneToOne: false
            referencedRelation: "tickets"
            referencedColumns: ["id"]
          },
        ]
      }
      clarifications: {
        Row: {
          answer: string | null
          answered_at: string | null
          asked_at: string
          created_at: string
          id: string
          options: Json
          question_id: string
          request_id: string
        }
        Insert: {
          answer?: string | null
          answered_at?: string | null
          asked_at?: string
          created_at?: string
          id?: string
          options?: Json
          question_id: string
          request_id: string
        }
        Update: {
          answer?: string | null
          answered_at?: string | null
          asked_at?: string
          created_at?: string
          id?: string
          options?: Json
          question_id?: string
          request_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "clarifications_request_id_fkey"
            columns: ["request_id"]
            isOneToOne: false
            referencedRelation: "requests"
            referencedColumns: ["id"]
          },
        ]
      }
      events: {
        Row: {
          action: string
          actor: string
          at: string
          created_at: string
          entity: string
          id: number
          payload: Json
        }
        Insert: {
          action: string
          actor: string
          at?: string
          created_at?: string
          entity: string
          id?: never
          payload?: Json
        }
        Update: {
          action?: string
          actor?: string
          at?: string
          created_at?: string
          entity?: string
          id?: never
          payload?: Json
        }
        Relationships: []
      }
      faq: {
        Row: {
          answer: string
          created_at: string
          embedding: string | null
          id: string
          is_demo: boolean
          lang: string
          question: string
          source_url: string | null
        }
        Insert: {
          answer: string
          created_at?: string
          embedding?: string | null
          id?: string
          is_demo?: boolean
          lang: string
          question: string
          source_url?: string | null
        }
        Update: {
          answer?: string
          created_at?: string
          embedding?: string | null
          id?: string
          is_demo?: boolean
          lang?: string
          question?: string
          source_url?: string | null
        }
        Relationships: []
      }
      incidents: {
        Row: {
          building_id: string
          category: string
          created_at: string
          id: string
          office: string | null
          opened_at: string
          priority: string
          report_count: number
          resolved_at: string | null
          status: string
          title: string
        }
        Insert: {
          building_id: string
          category: string
          created_at?: string
          id?: string
          office?: string | null
          opened_at?: string
          priority: string
          report_count?: number
          resolved_at?: string | null
          status?: string
          title?: string
        }
        Update: {
          building_id?: string
          category?: string
          created_at?: string
          id?: string
          office?: string | null
          opened_at?: string
          priority?: string
          report_count?: number
          resolved_at?: string | null
          status?: string
          title?: string
        }
        Relationships: [
          {
            foreignKeyName: "incidents_building_id_fkey"
            columns: ["building_id"]
            isOneToOne: false
            referencedRelation: "buildings"
            referencedColumns: ["id"]
          },
        ]
      }
      llm_calls: {
        Row: {
          cache_key: string | null
          cached: boolean
          cost_usd: number
          created_at: string
          id: string
          latency_ms: number | null
          model: string
          prompt_hash: string
          request_id: string | null
          response: Json | null
          tier: string | null
          tokens_in: number
          tokens_out: number
        }
        Insert: {
          cache_key?: string | null
          cached?: boolean
          cost_usd?: number
          created_at?: string
          id?: string
          latency_ms?: number | null
          model: string
          prompt_hash: string
          request_id?: string | null
          response?: Json | null
          tier?: string | null
          tokens_in?: number
          tokens_out?: number
        }
        Update: {
          cache_key?: string | null
          cached?: boolean
          cost_usd?: number
          created_at?: string
          id?: string
          latency_ms?: number | null
          model?: string
          prompt_hash?: string
          request_id?: string | null
          response?: Json | null
          tier?: string | null
          tokens_in?: number
          tokens_out?: number
        }
        Relationships: [
          {
            foreignKeyName: "llm_calls_request_id_fkey"
            columns: ["request_id"]
            isOneToOne: false
            referencedRelation: "requests"
            referencedColumns: ["id"]
          },
        ]
      }
      memory_examples: {
        Row: {
          active: boolean
          author_id: string | null
          category: string
          created_at: string
          embedding: string
          id: string
          lang: string
          priority: string
          text_norm: string
        }
        Insert: {
          active?: boolean
          author_id?: string | null
          category: string
          created_at?: string
          embedding: string
          id?: string
          lang: string
          priority: string
          text_norm: string
        }
        Update: {
          active?: boolean
          author_id?: string | null
          category?: string
          created_at?: string
          embedding?: string
          id?: string
          lang?: string
          priority?: string
          text_norm?: string
        }
        Relationships: []
      }
      notifications: {
        Row: {
          alias: string
          created_at: string
          id: string
          kind: string
          payload: Json
          read_at: string | null
        }
        Insert: {
          alias: string
          created_at?: string
          id?: string
          kind: string
          payload?: Json
          read_at?: string | null
        }
        Update: {
          alias?: string
          created_at?: string
          id?: string
          kind?: string
          payload?: Json
          read_at?: string | null
        }
        Relationships: []
      }
      outbox: {
        Row: {
          alias: string | null
          body: string
          channel: string
          created_at: string
          error: string | null
          flags: string[]
          id: string
          kind: string
          priority: string | null
          provider_id: string | null
          request_id: string | null
          status: string
          subject: string
          to_address: string
        }
        Insert: {
          alias?: string | null
          body?: string
          channel?: string
          created_at?: string
          error?: string | null
          flags?: string[]
          id?: string
          kind?: string
          priority?: string | null
          provider_id?: string | null
          request_id?: string | null
          status: string
          subject?: string
          to_address: string
        }
        Update: {
          alias?: string | null
          body?: string
          channel?: string
          created_at?: string
          error?: string | null
          flags?: string[]
          id?: string
          kind?: string
          priority?: string | null
          provider_id?: string | null
          request_id?: string | null
          status?: string
          subject?: string
          to_address?: string
        }
        Relationships: [
          {
            foreignKeyName: "outbox_request_id_fkey"
            columns: ["request_id"]
            isOneToOne: false
            referencedRelation: "requests"
            referencedColumns: ["id"]
          },
        ]
      }
      predictions: {
        Row: {
          artifact_version: string | null
          category: string | null
          core: Json | null
          cost_usd: number | null
          created_at: string
          explanation: Json | null
          flags: string[]
          id: string
          latency_ms: number | null
          models_used: string[] | null
          p_cat: Json | null
          p_pri: Json | null
          per_model: Json | null
          priority: string | null
          request_id: string
          set_cat: string[] | null
          set_pri: string[] | null
          tier: string | null
        }
        Insert: {
          artifact_version?: string | null
          category?: string | null
          core?: Json | null
          cost_usd?: number | null
          created_at?: string
          explanation?: Json | null
          flags?: string[]
          id?: string
          latency_ms?: number | null
          models_used?: string[] | null
          p_cat?: Json | null
          p_pri?: Json | null
          per_model?: Json | null
          priority?: string | null
          request_id: string
          set_cat?: string[] | null
          set_pri?: string[] | null
          tier?: string | null
        }
        Update: {
          artifact_version?: string | null
          category?: string | null
          core?: Json | null
          cost_usd?: number | null
          created_at?: string
          explanation?: Json | null
          flags?: string[]
          id?: string
          latency_ms?: number | null
          models_used?: string[] | null
          p_cat?: Json | null
          p_pri?: Json | null
          per_model?: Json | null
          priority?: string | null
          request_id?: string
          set_cat?: string[] | null
          set_pri?: string[] | null
          tier?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "predictions_request_id_fkey"
            columns: ["request_id"]
            isOneToOne: false
            referencedRelation: "requests"
            referencedColumns: ["id"]
          },
        ]
      }
      profiles: {
        Row: {
          alias: string | null
          id: string
          office: string | null
          role: string
        }
        Insert: {
          alias?: string | null
          id: string
          office?: string | null
          role?: string
        }
        Update: {
          alias?: string | null
          id?: string
          office?: string | null
          role?: string
        }
        Relationships: []
      }
      redteam_runs: {
        Row: {
          config: Json
          created_at: string
          id: string
          scorecard: Json
        }
        Insert: {
          config?: Json
          created_at?: string
          id?: string
          scorecard?: Json
        }
        Update: {
          config?: Json
          created_at?: string
          id?: string
          scorecard?: Json
        }
        Relationships: []
      }
      request_embeddings: {
        Row: {
          building_id: string | null
          category: string | null
          created_at: string
          embedding: string
          lang: string | null
          priority: string | null
          request_id: string
          room: string | null
        }
        Insert: {
          building_id?: string | null
          category?: string | null
          created_at?: string
          embedding: string
          lang?: string | null
          priority?: string | null
          request_id: string
          room?: string | null
        }
        Update: {
          building_id?: string | null
          category?: string | null
          created_at?: string
          embedding?: string
          lang?: string | null
          priority?: string | null
          request_id?: string
          room?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "request_embeddings_building_id_fkey"
            columns: ["building_id"]
            isOneToOne: false
            referencedRelation: "buildings"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "request_embeddings_request_id_fkey"
            columns: ["request_id"]
            isOneToOne: true
            referencedRelation: "requests"
            referencedColumns: ["id"]
          },
        ]
      }
      requests: {
        Row: {
          alias: string | null
          building_id: string | null
          conversation_id: string | null
          core: string | null
          created_at: string
          id: string
          input_mode: string | null
          is_arabizi: boolean | null
          lang: string | null
          location_source: string | null
          model_text: string | null
          raw_text: string
          room: string | null
          simulated: boolean
          stated_urgency: boolean | null
          status: string
          text_norm: string | null
          truncated: boolean
        }
        Insert: {
          alias?: string | null
          building_id?: string | null
          conversation_id?: string | null
          core?: string | null
          created_at?: string
          id?: string
          input_mode?: string | null
          is_arabizi?: boolean | null
          lang?: string | null
          location_source?: string | null
          model_text?: string | null
          raw_text: string
          room?: string | null
          simulated?: boolean
          stated_urgency?: boolean | null
          status: string
          text_norm?: string | null
          truncated?: boolean
        }
        Update: {
          alias?: string | null
          building_id?: string | null
          conversation_id?: string | null
          core?: string | null
          created_at?: string
          id?: string
          input_mode?: string | null
          is_arabizi?: boolean | null
          lang?: string | null
          location_source?: string | null
          model_text?: string | null
          raw_text?: string
          room?: string | null
          simulated?: boolean
          stated_urgency?: boolean | null
          status?: string
          text_norm?: string | null
          truncated?: boolean
        }
        Relationships: [
          {
            foreignKeyName: "requests_building_id_fkey"
            columns: ["building_id"]
            isOneToOne: false
            referencedRelation: "buildings"
            referencedColumns: ["id"]
          },
        ]
      }
      review_queue: {
        Row: {
          corrected_category: string | null
          corrected_priority: string | null
          created_at: string
          id: string
          note: string | null
          prediction_id: string
          reason: string
          resolved_at: string | null
          reviewer_id: string | null
          status: string
        }
        Insert: {
          corrected_category?: string | null
          corrected_priority?: string | null
          created_at?: string
          id?: string
          note?: string | null
          prediction_id: string
          reason: string
          resolved_at?: string | null
          reviewer_id?: string | null
          status?: string
        }
        Update: {
          corrected_category?: string | null
          corrected_priority?: string | null
          created_at?: string
          id?: string
          note?: string | null
          prediction_id?: string
          reason?: string
          resolved_at?: string | null
          reviewer_id?: string | null
          status?: string
        }
        Relationships: [
          {
            foreignKeyName: "review_queue_prediction_id_fkey"
            columns: ["prediction_id"]
            isOneToOne: false
            referencedRelation: "predictions"
            referencedColumns: ["id"]
          },
        ]
      }
      student_signals: {
        Row: {
          alias: string
          created_at: string
          gaming_flag: boolean
          n_claimed_urgent: number
          n_claimed_urgent_not_high: number
          n_high: number
          n_injection: number
          n_requests: number
          updated_at: string
        }
        Insert: {
          alias: string
          created_at?: string
          gaming_flag?: boolean
          n_claimed_urgent?: number
          n_claimed_urgent_not_high?: number
          n_high?: number
          n_injection?: number
          n_requests?: number
          updated_at?: string
        }
        Update: {
          alias?: string
          created_at?: string
          gaming_flag?: boolean
          n_claimed_urgent?: number
          n_claimed_urgent_not_high?: number
          n_high?: number
          n_injection?: number
          n_requests?: number
          updated_at?: string
        }
        Relationships: []
      }
      ticket_links: {
        Row: {
          created_at: string
          external_id: string
          external_url: string | null
          last_error: string | null
          last_synced_at: string | null
          sink: string
          ticket_id: string
        }
        Insert: {
          created_at?: string
          external_id: string
          external_url?: string | null
          last_error?: string | null
          last_synced_at?: string | null
          sink: string
          ticket_id: string
        }
        Update: {
          created_at?: string
          external_id?: string
          external_url?: string | null
          last_error?: string | null
          last_synced_at?: string | null
          sink?: string
          ticket_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "ticket_links_ticket_id_fkey"
            columns: ["ticket_id"]
            isOneToOne: false
            referencedRelation: "tickets"
            referencedColumns: ["id"]
          },
        ]
      }
      tickets: {
        Row: {
          body: string
          category: string
          created_at: string
          escalated_at: string | null
          id: string
          incident_id: string | null
          office: string
          priority: string
          provisional: boolean
          request_id: string
          resolved_at: string | null
          sla_due_at: string
          status: string
          title: string
        }
        Insert: {
          body?: string
          category: string
          created_at?: string
          escalated_at?: string | null
          id?: string
          incident_id?: string | null
          office: string
          priority: string
          provisional?: boolean
          request_id: string
          resolved_at?: string | null
          sla_due_at: string
          status?: string
          title?: string
        }
        Update: {
          body?: string
          category?: string
          created_at?: string
          escalated_at?: string | null
          id?: string
          incident_id?: string | null
          office?: string
          priority?: string
          provisional?: boolean
          request_id?: string
          resolved_at?: string | null
          sla_due_at?: string
          status?: string
          title?: string
        }
        Relationships: [
          {
            foreignKeyName: "tickets_incident_id_fkey"
            columns: ["incident_id"]
            isOneToOne: false
            referencedRelation: "incidents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "tickets_request_id_fkey"
            columns: ["request_id"]
            isOneToOne: false
            referencedRelation: "requests"
            referencedColumns: ["id"]
          },
        ]
      }
    }
    Views: {
      faq_v: {
        Row: {
          answer: string | null
          id: string | null
          is_demo: boolean | null
          lang: string | null
          question: string | null
          source_url: string | null
        }
        Insert: {
          answer?: string | null
          id?: string | null
          is_demo?: boolean | null
          lang?: string | null
          question?: string | null
          source_url?: string | null
        }
        Update: {
          answer?: string | null
          id?: string | null
          is_demo?: boolean | null
          lang?: string | null
          question?: string | null
          source_url?: string | null
        }
        Relationships: []
      }
      memory_examples_v: {
        Row: {
          active: boolean | null
          author_id: string | null
          category: string | null
          created_at: string | null
          id: string | null
          lang: string | null
          priority: string | null
          text_norm: string | null
        }
        Insert: {
          active?: boolean | null
          author_id?: string | null
          category?: string | null
          created_at?: string | null
          id?: string | null
          lang?: string | null
          priority?: string | null
          text_norm?: string | null
        }
        Update: {
          active?: boolean | null
          author_id?: string | null
          category?: string | null
          created_at?: string | null
          id?: string | null
          lang?: string | null
          priority?: string | null
          text_norm?: string | null
        }
        Relationships: []
      }
      predictions_student_v: {
        Row: {
          artifact_version: string | null
          category: string | null
          created_at: string | null
          explanation: Json | null
          flags: string[] | null
          id: string | null
          p_cat: Json | null
          p_pri: Json | null
          priority: string | null
          request_id: string | null
          set_cat: string[] | null
          set_pri: string[] | null
          tier: string | null
        }
        Relationships: []
      }
    }
    Functions: {
      bump_student_signals: {
        Args: {
          p_alias: string
          p_claimed_urgent: boolean
          p_injection: boolean
          p_was_high: boolean
        }
        Returns: {
          alias: string
          created_at: string
          gaming_flag: boolean
          n_claimed_urgent: number
          n_claimed_urgent_not_high: number
          n_high: number
          n_injection: number
          n_requests: number
          updated_at: string
        }
        SetofOptions: {
          from: "*"
          to: "student_signals"
          isOneToOne: true
          isSetofReturn: false
        }
      }
      match_vectors: {
        Args: {
          p_collection: string
          p_filters?: Json
          p_k: number
          p_min_sim?: number
          p_query: string
        }
        Returns: {
          embedding: string
          id: string
          lang: string
          meta: Json
          sim: number
          text: string
        }[]
      }
      vector_dim: { Args: never; Returns: number }
    }
    Enums: {
      [_ in never]: never
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
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never) = never,
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
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never) = never,
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
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never) = never,
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
  EnumName extends (DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never) = never,
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
  CompositeTypeName extends (PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never) = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  public: {
    Enums: {},
  },
} as const
