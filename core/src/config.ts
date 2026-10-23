/** Configuração do classificador. Os nomes espelham o config.json do hic.py para a migração ser direta. */
export type UnknownPolicy = "log" | "block" | "allow";

export interface ClassifierConfig {
  away_after_min: number;
  /** Ociosidade (min) a partir da qual o minuto deixa de contar como trabalho. Corrige o ar do contador. */
  idle_work_max_min: number;
  browser_app: string;
  work_apps: string[];
  blocked_apps: string[];
  neutral_apps: string[];
  work_domains: string[];
  blocked_domains: string[];
  private_domains: string[];
  private_patterns: string[];
  unknown_domain_policy: UnknownPolicy;
  unknown_app_policy: UnknownPolicy;
}

/** Defaults genéricos. Nada aqui é específico de uma pessoa ou empresa; cada usuário ajusta no próprio config. */
export const DEFAULT_CONFIG: ClassifierConfig = {
  away_after_min: 45,
  idle_work_max_min: 10,
  browser_app: "Google Chrome",
  work_apps: ["Code", "Visual Studio Code", "Cursor", "Terminal", "iTerm2", "Xcode", "Figma", "Slack", "Notion", "Linear"],
  blocked_apps: ["Steam", "Netflix", "Minecraft"],
  neutral_apps: ["Finder", "System Settings", "Calendar", "Spotify", "Music"],
  work_domains: ["github.com", "gitlab.com", "stackoverflow.com", "localhost", "127.0.0.1", "docs.google.com", "mail.google.com", "meet.google.com"],
  blocked_domains: ["youtube.com", "twitter.com", "x.com", "instagram.com", "reddit.com", "netflix.com"],
  private_domains: [],
  private_patterns: [],
  unknown_domain_policy: "log",
  unknown_app_policy: "log",
};
