{{#if title}}
# {{ title }}
{{/if}}

{{#if subtitle}}
## <span class="cmp-subtitle">{{ subtitle }}</span>
{{/if}}

<div class="cmp-container">

{{#each sections}}
<div class="cmp-card">

  {{#if this.title}}
  <div class="cmp-card-title">{{ this.title }}</div>
  {{/if}}

  <table class="cmp-table">
    <thead>
      <tr>
        {{#each ../columns}}
        <th class="cmp-head cmp-col-{{ @index }}">
          {{ this }}
        </th>
        {{/each}}
      </tr>
    </thead>

    <tbody>
      {{#each this.rows}}
      <tr>
        {{#each this}}
        <td class="cmp-cell cmp-col-{{ @index }}">
          <div class="cmp-cell-title">{{ this.title }}</div>
          <div class="cmp-cell-content">{{ this.content }}</div>
        </td>
        {{/each}}
      </tr>
      {{/each}}
    </tbody>
  </table>

</div>
{{/each}}

</div>
