import { UIAbility, Want } from '@kit.AbilityKit';
import { window } from '@kit.ArkUI';
export default class EntryAbility extends UIAbility {
  onCreate(want: Want): void { this.receive(want); }
  onNewWant(want: Want): void { this.receive(want); }
  private receive(want: Want): void {
    if (want.uri && /^foodcrowd:\/\/join\/?#invite=[a-f0-9]{64}$/.test(want.uri)) AppStorage.setOrCreate('crowdInvite', want.uri);
  }
  onWindowStageCreate(stage: window.WindowStage): void { stage.loadContent('pages/Index'); }
}
