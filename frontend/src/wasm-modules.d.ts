// Type declarations for optional/wasm modules
declare module 'openwakeword-wasm' {
  export default class OpenWakeWord {
    init(): Promise<void>;
    createDetector(config: { model: string; sensitivity: number }): Promise<any>;
  }
}