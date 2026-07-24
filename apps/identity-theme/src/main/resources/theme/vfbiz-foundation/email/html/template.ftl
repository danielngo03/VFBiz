<#macro emailLayout>
<!doctype html>
<html lang="${locale.language}" dir="${(ltr)?then('ltr','rtl')}">
  <body style="margin:0;padding:0;background:#f1f4f8;color:#142033;font-family:Arial,sans-serif">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f1f4f8;padding:32px 16px">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:600px;border:1px solid #d8e0ea;border-radius:14px;background:#ffffff">
            <tr>
              <td style="padding:28px 32px 12px;font-size:20px;font-weight:700">
                VFBiz
              </td>
            </tr>
            <tr>
              <td style="padding:12px 32px 28px;font-size:16px;line-height:1.6">
                <#nested>
              </td>
            </tr>
            <tr>
              <td style="border-top:1px solid #d8e0ea;padding:20px 32px;color:#5c6979;font-size:13px;line-height:1.5">
                ${msg("emailFooter")}
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
</#macro>
